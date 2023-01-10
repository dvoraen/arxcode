"""
commands.base_commands.settings

This module defines the "settings" command and those related to the user experience.
"""


from collections import namedtuple

from django.core.exceptions import FieldDoesNotExist
from evennia import EvTable, InterruptCommand

from commands.base import ArxCommand
from world.settings.models import AllSettings, CommSettings, GeneralSettings, RPSettings


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
      settings all                     - shows all settings
      settings rp/emit_label=on        - sets emit_label in category "rp" to on
      settings/find msg                - find all settings with "msg" in the name
      settings/apply all=Alt           - applies all of your settings to Alt
      settings/apply rp=Alt            - applies each "rp" setting to Alt
      settings/apply rp/emit_label=Alt - applies "rp" emit_label setting to Alt
    """

    key = "settings"
    locks = "cmd:all()"
    help_category = "Settings"

    switch_options = ("find", "apply")

    model_map = {
        # This is a map between the command's categories and the models.
        # Largely used towards calling get_table() and _meta.get_field() for
        # each category.
        "all": AllSettings,
        "general": GeneralSettings,
        "comm": CommSettings,
        "rp": RPSettings,
        # "craft": CraftSettings,
        # "bank": BankSettings,
    }

    error_msgs = {
        "usage_category": "Usage: settings <category>",
        "usage_setting": "Usage: settings <category>/<setting_name>=<value>",
        "usage_find": "Usage: settings/find <setting_name>",
        "usage_apply": "Usage: settings/apply <category>[/<setting_name>]=<character>",
        "invalid_category": "{category} is not a valid settings category.\nCategories: {valid_categories}",
        "invalid_setting_category": '"all" is not a valid category for setting a specific setting.\nUse settings/find to find that setting\'s category.',
        "invalid_setting_name": "'{setting_name}' is not a setting in category '{category}'.",
        "no_settings_found": 'No settings found with names containing "{setting_name}"',
        "setting_not_configured": "Your character doesn't have settings configured for '{category}'.\n|w*** Notify staff of this problem. ***|n",
    }

    # User input set by parse():
    category: str
    setting_name: str

    def parse(self):
        super().parse()

        self.category = None
        self.setting_name = None

        self.settings = {
            "all": self.caller.settings,
            "general": self.caller.settings.general,
            "rp": self.caller.settings.rp,
            "comm": self.caller.settings.comm,
        }

        # If we're finding a setting, we "should" just have a setting_name
        # in the input/args and that's all we need to do here.
        if "find" in self.switches:
            self.setting_name = self.args.lower()
            return

        # Parse lhs; it's the only "dynamic" part of the command that
        # needs attention.
        if "/" in self.lhs:
            self.category, self.setting_name = self.lhs.split("/", 1)
        else:
            self.category = self.lhs

        self.category = self.category.lower() if self.category else None
        self.setting_name = self.category.lower() if self.setting_name else None

    def func(self):
        # This command always requires input beyond the command name.
        if not self.args:
            response = "\n".join(
                (
                    self.error_msgs["usage_category"],
                    self.error_msgs["usage_setting"],
                    self.error_msgs["usage_find"],
                    self.error_msgs["usage_apply"],
                )
            )
            self.caller.msg(response)
            raise InterruptCommand

        if "find" in self.switches:
            self.find()
        elif "apply" in self.switches:
            self.apply()
        else:
            # If we have a setting name with a category, then user is
            # intending to set a setting.  Otherwise, just display
            # that setting or category.
            if self.category and self.setting_name and self.rhs:
                self.set_setting()
            elif self.category and self.setting_name and not self.rhs:
                self.display_setting()
            else:
                self.display_category()

    def validate_category(self):
        """
        Validates the input category against those defined in CmdSettings.model_map.
        """

        if self.category not in self.model_map.keys():
            response = self.error_msgs["invalid_category"].format(
                category=self.category,
                valid_categories=", ".join(self.model_map.keys()),
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
            self.caller.msg(self.model_map["invalid_setting_category"])
            raise InterruptCommand

        # Validate whether setting exists on the model.
        settings = self.settings[self.category]
        if not settings.has_setting(self.setting_name):
            response = self.error_msgs["invalid_setting_name"].format(
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
        self.validate_category()

        table = self.settings[self.category].get_table()
        self.caller.msg(table)

    def display_setting(self):
        """
        Displays the requested setting, its help_text, and current value.
        """
        self.validate_category()
        self.validate_setting()

        settings = self.settings[self.category]
        setting_field = settings._meta.get_field(self.setting_name)
        setting_value = getattr(settings, self.setting_name)

        table = EvTable(border=None)
        table.add_row(setting_field.name, setting_field.help_text, setting_value)
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
        for category, model in self.model_map.items():
            # Nothing to be found in "all"; move on.
            if category == "all":
                continue

            fields = model._meta.get_fields()

            category_settings = [
                FoundSetting(
                    name=field.name, category=category, help_text=field.help_text
                )
                for field in fields
                if self.setting_name in field.name
            ]

            found_settings.extend(category_settings)

        if not found_settings:
            response = self.error_msgs["no_settings_found"].format(
                setting_name=self.setting_name
            )
            self.caller.msg(response)
            raise InterruptCommand

        table = EvTable(
            f'|wResults for "{self.setting_name}"|n',
            border="tablecols",
            header_line_char="-",
            valign="t",
        )

        for setting in found_settings:
            table.add_row(setting.name, setting.category, setting.help_text)

        # Header row and last row have no padding at the bottom.
        for column in table.table:
            column.reformat(pad_bottom=1)
            column.reformat_cell(0, pad_bottom=0)
            column.reformat_cell(table.nrows - 1, pad_bottom=0)

        # Setting name and category are centered and top-aligned.
        # The help_text is just top (and left/default) aligned.
        table.table[0].reformat(align="c")
        table.table[1].reformat(align="c")
        table.table[2].reformat(width=40)

        self.caller.msg(table)

    def apply(self):
        """
        Applies specified setting(s) to specified alt, if that character IS
        an alt of the caller.
        """
        # Applying settings to an alt may require me to change my models such that
        # each category has a 1to1 to the owning character.  It would be easy to get
        # category settings for the alt, then, and perhaps with lower database interaction
        # than chaining through models to get to the required settings.
        self.validate_category()
        if self.setting_name is not None:
            self.validate_setting()
        self.validate_alt()

        # Alt was validated, so self.rhs should be okay.
        # Get alt's settings model instance.
        # Apply caller's specified setting(s) to alt settings.

    def set_setting(self):
        """
        Sets the specified setting for the caller.
        """
        self.validate_category()
        self.validate_setting()
