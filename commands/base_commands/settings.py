"""
commands.base_commands.settings

This module defines the "settings" command and those related to the user experience.
"""


from collections import namedtuple

from django.core.exceptions import ValidationError
from evennia import EvTable, InterruptCommand

from commands.base import ArxCommand
from world.settings.models import (
    CommSettings,
    GeneralSettings,
    PlayerSettings,
    RPSettings,
)


class CmdSettings(ArxCommand):
    """
    settings

    Manages your Arx gameplay settings.

    Syntax:
      settings <category>
      settings <category>/<setting_name>=<value>

      settings/find <partial_setting_name>
      settings/apply <category>=<character>
      settings/apply <category>/<setting_name>=<character>

    Switches:
      (none) - displays the settings in the specified category
      /find  - returns the setting names, categories, and descriptions
               for settings containing the provided string
      /apply - applies the given category or setting to the given (alt)
               character

    Categories:
      all
      general - settings related to Arx gameplay (game output)
      comm    - settings related to communication (channels, pages, messages)
      rp      - settings related to RP (emits/poses)

    Examples:
      settings all           - shows all settings
      settings rp/color=|g   - sets color setting in rp category to |g
      settings/find msg      - find all settings with "msg" in the name
      settings/apply all=Alt - applies all of your settings to Alt
      settings/apply rp=Alt  - applies each rp setting to Alt
    """

    key = "settings"
    locks = "cmd:all()"
    help_category = "Settings"

    switch_options = ("find", "apply")

    cmd_msgs = {
        "usage_msg": "Usage:{syntax_msg}",
        "syntax_category": "settings <category>",
        "syntax_setting": "settings <category>/<setting_name>=<value>",
        "syntax_find": "settings/find <setting_name>",
        "syntax_apply": "settings/apply <category>[/<setting_name>]=<character>",
        "invalid_category": "{category} is not a valid settings category.\nCategories: {valid_categories}",
        "invalid_setting_category": '"all" is not a valid category for setting a specific setting.\nUse settings/find to find that setting\'s category.',
        "invalid_setting_name": "{setting_name} is not a setting in category '{category}'.",
        "no_settings_found": 'No settings found with names containing "{setting_name}"',
        "setting_not_configured": "Your character doesn't have settings configured for category '{category}'.\n|w*** Notify staff of this problem. ***|n",
        "setting_set": "{category}/{setting_name} set to {setting_value}.",
    }

    def parse(self):
        super().parse()

        SettingsTuple = namedtuple("SettingsTuple", ["settings", "model"])

        self.category: str = None
        self.setting_name: str = None
        self.alt_name: str = None

        self.settings_map = {
            "all": SettingsTuple(settings=self.caller.settings, model=PlayerSettings),
            "general": SettingsTuple(
                settings=self.caller.settings.general, model=GeneralSettings
            ),
            "rp": SettingsTuple(settings=self.caller.settings.rp, model=RPSettings),
            "comm": SettingsTuple(
                settings=self.caller.settings.comm, model=CommSettings
            ),
        }

        # Validate syntax.
        usage_keys = ()
        if "find" in self.switches:
            # If we're finding a setting, we should just have a setting_name
            # in the input/args and that's all we need to do here.
            if not self.args:
                usage_keys = ("syntax_find",)
            else:
                self.setting_name = self.args
        elif "apply" in self.switches:
            # If we're applying a setting, we need to have both lhs and rhs.
            if not self.args or not self.rhs:
                usage_keys = ("syntax_apply",)
            else:
                self.category, self.setting_name = self.parse_lhs()
                self.alt_name = self.rhs
        else:
            # If we're looking for a category or a specific setting...
            if not self.args:
                usage_keys = ("syntax_category", "syntax_setting")
            else:
                self.category, self.setting_name = self.parse_lhs()

        # If we have any syntax errors that requires notifying the caller of
        # the command's usage, do so and end the command.
        if usage_keys:
            if len(usage_keys) == 1:
                syntax_msg = f" {self.cmd_msgs[usage_keys[0]]}"
            else:
                syntax_msg = "\n" + "\n".join(
                    (f"  {self.cmd_msgs[key]}" for key in usage_keys)
                )

            response = self.cmd_msgs["usage_msg"].format(syntax_msg=syntax_msg)
            self.caller.msg(response)
            raise InterruptCommand

        # Format the user input accordingly.
        self.category = self.category.lower() if self.category else None
        self.setting_name = self.setting_name.lower() if self.setting_name else None
        self.alt_name = self.alt_name.title() if self.alt_name else None

    def parse_lhs(self):
        # Parse lhs; it's the only "dynamic" part of the command that
        # needs attention.
        if "/" in self.lhs:
            category, setting_name = self.lhs.split("/", 1)
            return category, setting_name
        else:
            return self.lhs, None

    def func(self):
        self.validate()

        if "find" in self.switches:
            self.find()
        elif "apply" in self.switches:
            self.apply()
        else:
            # If we have a setting name with a category and value, then user is
            # intending to set a setting.  Otherwise, just display
            # that setting or category.
            if self.category and self.setting_name and self.rhs:
                self.set_setting()
            elif self.category and self.setting_name and not self.rhs:
                self.display_setting()
            else:
                self.display_category()

    def validate(self):
        if not self.switches:
            # If we're just looking at a category, validate it.
            # If we're looking at a specific setting, validate the setting too.
            self.validate_category()
            if self.setting_name:
                self.validate_setting()
        elif "find" in self.switches:
            # If we're finding a setting, we don't need to validate anything at this time.
            # The (sub)string entered by the caller is searched.
            pass
        elif "apply" in self.switches:
            # If we're applying a category, the category and alt need to be validated.
            # If we're applying a specific setting, the setting needs validated too.
            self.validate_category()
            if self.setting_name:
                self.validate_setting()
            self.validate_alt()

    def validate_category(self):
        """
        Validates the input category against those defined in settings_map.
        """

        if self.category not in self.settings_map.keys():
            response = self.cmd_msgs["invalid_category"].format(
                category=self.category,
                valid_categories=", ".join(self.settings_map.keys()),
            )
            self.caller.msg(response)
            raise InterruptCommand

    def validate_setting(self):
        """
        Validates the input setting name against the model fields of the given
        (not-"all") category.

        Precondition:
        - The category was validated.
        """

        # Settings don't directly exist in the 'all' category; it's invalid.
        if self.category == "all":
            self.caller.msg(self.cmd_msgs["invalid_setting_category"])
            raise InterruptCommand

        # Validate whether setting exists on the model.
        settings = self.settings_map[self.category].settings
        if not settings.has_setting(self.setting_name):
            response = self.cmd_msgs["invalid_setting_name"].format(
                category=self.category, setting_name=self.setting_name
            )
            self.caller.msg(response)
            raise InterruptCommand

    def validate_alt(self):
        # TODO: Implement me.
        pass

    def display_category(self):
        """
        Displays the table or tables for the specified category, showing the
        caller's settings.
        """
        table = self.settings_map[self.category].settings.get_table()
        self.caller.msg(table)

    def display_setting(self):
        """
        Displays the requested setting, its help_text, and current value.
        """
        settings = self.settings_map[self.category].settings
        setting_field = settings._meta.get_field(self.setting_name)
        setting_value = settings.get_setting_value(self.setting_name)

        table = EvTable(border="tablecols", valign="t")
        table.add_row(setting_field.name, setting_field.help_text, setting_value)

        table.table[0].reformat(align="c")
        table.table[1].reformat(width=40)
        table.table[2].reformat(align="c")

        self.caller.msg(table)

    def find(self):
        """
        Finds all settings with the given setting name and displays a table
        with the settings' names, categories, and help_text.
        """
        FoundSetting = namedtuple("FoundSetting", ["name", "category", "help_text"])

        found_settings = []
        # For each model in our settings library, look for a field with
        # that setting's name.  If it exists, add it to the list.
        for category, setting_tuple in self.settings_map.items():
            # Nothing to be found in "all"; move on.
            if category == "all":
                continue

            fields = setting_tuple.model._meta.get_fields()

            category_settings = [
                FoundSetting(
                    name=field.name, category=category, help_text=field.help_text
                )
                for field in fields
                if self.setting_name in field.name
            ]

            found_settings.extend(category_settings)

        if not found_settings:
            response = self.cmd_msgs["no_settings_found"].format(
                setting_name=self.setting_name
            )
            self.caller.msg(response)
            raise InterruptCommand

        table = EvTable(valign="t")

        for setting in found_settings:
            table.add_row(setting.name, setting.category, setting.help_text)

        # Last row has no padding at the bottom.
        for column in table.table:
            column.reformat(pad_bottom=1)
            column.reformat_cell(table.nrows - 1, pad_bottom=0)

        # Setting name and category are centered and top-aligned.
        # The help_text is just top (and left/default) aligned.
        table.table[0].reformat(align="c")
        table.table[1].reformat(align="c")
        table.table[2].reformat(width=40)

        response = f'|wResults for "{self.setting_name}"|n\n{table}'
        self.caller.msg(response)

    def apply(self):
        """
        Applies specified setting(s) to specified alt, if that character IS
        an alt of the caller.
        """
        # Steps:
        # - Get alt char's settings.
        # - Put settings and their categories to apply in a list.
        # - For each setting in list, setattr() on alt.
        pass

    def set_setting(self):
        """
        Sets the specified setting for the caller.
        """
        try:
            settings = self.settings_map[self.category].settings
            setattr(settings, self.setting_name, self.rhs)
            settings.save()
        except ValidationError as error:
            self.caller.msg("\n".join(error.messages))
            raise InterruptCommand

        response = self.cmd_msgs["setting_set"].format(
            category=self.category,
            setting_name=self.setting_name,
            setting_value=settings.get_setting_value(self.setting_name),
        )
        self.caller.msg(response)
