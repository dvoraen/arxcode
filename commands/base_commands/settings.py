"""
commands.base_commands.settings

This module defines the "settings" command and those related to the user experience.
"""


from typing import List, Optional, Tuple

from evennia import EvTable, InterruptCommand

from commands.base import ArxCommand
from typeclasses.accounts import Account
from typeclasses.characters import Character
from world.settings.models import (
    CharacterSettings,
    SettingTuple,
    SettingsError,
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
      (none)   - displays the settings in the specified category
      /find    - returns the setting names, categories, and descriptions
                 for settings containing the provided string
      /apply   - applies the given category or setting to the given (alt)
                 character

    Categories:
      all
      account - settings that affect your account
      general - settings related to Arx gameplay (game output)
      comm    - settings related to communication (channels, pages, messages)
      rp      - settings related to RP (emits/poses)

    Examples:
      settings all           - shows all settings
      settings rp/color=|g   - sets "color" in rp category to |g
      settings/find msg      - find all settings with "msg" in the name
      settings/apply all=Alt - applies all of your character settings to Alt
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
        "invalid_category": "{category} is not a valid settings category.\n(valid categories: {valid_categories})",
        "all_not_valid": '"all" is not a valid category for setting a specific setting.\nUse settings/find to find that setting\'s category.',
        "invalid_setting_name": "{setting_name} is not a setting in category '{category}'.",
        "invalid_alt": "{alt_name} is not one of your characters.",
        "no_settings_found": 'No settings found with names containing "{setting_name}"',
        "setting_not_configured": "Your character doesn't have settings data set up for category '{category}'.\n|w*** Notify staff of this problem. ***|n",
        "find_results": '|wResults for "{setting_name}"|n\n{table}',
        "setting_set": "{category}/{setting_name} set to {setting_value}.",
        "applied_category": "Applied {category} settings to {alt_name}.",
        "applied_setting": "Applied {category}/{setting_name} setting to {alt_name}.",
        "alt_applied_category": "{category} settings were applied by {character}.",
        "alt_applied_setting": "Setting '{category}/{setting_name}' ({value}) was applied by {character}.",
    }

    def parse(self):
        super().parse()

        self.account: Account = self.caller.player_ob
        self.character: Character = self.caller.char_ob
        self.settings: CharacterSettings = self.character.settings
        self.alt: Optional[Character] = None

        # Check for invalid syntax.
        usage_keys: Tuple[str] = ()
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
                self.category_name, self.setting_name = self._parse_lhs()
                self.alt_name = self.rhs
        else:
            # If we're looking for a category or a specific setting...
            if not self.args:
                usage_keys = (
                    "syntax_category",
                    "syntax_setting",
                    "syntax_find",
                    "syntax_apply",
                )
            else:
                self.category_name, self.setting_name = self._parse_lhs()

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
        self.category_name = self.category_name.lower() if self.category_name else ""
        self.setting_name = self.setting_name.lower() if self.setting_name else ""
        self.alt_name = self.alt_name.title() if self.alt_name else ""

    def _parse_lhs(self):
        # Parse lhs; it's the only "dynamic" part of the command that
        # needs attention.
        if "/" in self.lhs:
            category, setting_name = self.lhs.split("/", 1)
            return category, setting_name
        else:
            return self.lhs, None

    def func(self):
        self._validate()

        if "find" in self.switches:
            self._find()
        elif "apply" in self.switches:
            self._apply()
        else:
            # If we have a setting name with a category and value, then user is
            # intending to set a setting.  Otherwise, just display
            # that setting or category.
            if self.category_name and self.setting_name and self.rhs:
                self._set_setting()
            elif self.category_name and self.setting_name and not self.rhs:
                self._display_setting()
            else:
                self._display_category()

    def _validate(self):
        if not self.switches:
            # If we're just looking at a category, validate it.
            # If we're looking at a specific setting, validate the setting too.
            self._validate_category()
            if self.setting_name:
                self._validate_setting()
        elif "find" in self.switches:
            # If we're finding a setting, we don't need to validate anything at this time.
            # The (sub)string entered by the caller is searched.
            pass
        elif "apply" in self.switches:
            # If we're applying a category, the category and alt need to be validated.
            # If we're applying a specific setting, the setting needs validated too.
            self._validate_category()
            if self.setting_name:
                self._validate_setting()
            self._validate_alt()

    def _validate_category(self):
        """
        Validates the input category against those defined in valid_categories.
        """
        valid_categories = self.settings.valid_categories

        if self.category_name not in valid_categories:
            response = self.cmd_msgs["invalid_category"].format(
                category=self.category_name,
                valid_categories=", ".join(valid_categories),
            )
            self.caller.msg(response)
            raise InterruptCommand

    def _validate_setting(self):
        """
        Validates the input setting name against the model fields of the given
        (not-"all") category.

        Precondition:
        - The category was validated.
        """
        # Settings don't directly exist in the 'all' category; it's invalid.
        if self.category_name == "all":
            self.caller.msg(self.cmd_msgs["all_not_valid"])
            raise InterruptCommand

        # Validate whether setting exists on the model.
        category = self.settings.get_category(self.category_name)
        if not category.has_setting(self.setting_name):
            response = self.cmd_msgs["invalid_setting_name"].format(
                category=self.category_name, setting_name=self.setting_name
            )
            self.caller.msg(response)
            raise InterruptCommand

    def _validate_alt(self):
        """
        Validates that the input alt name is also a character played by the caller.
        """
        alt_names = (character.key.lower() for character in self.character.alts)

        # Validate if given alt name is among those attached to the account.
        if self.alt_name.lower() not in alt_names:
            response = self.cmd_msgs["invalid_alt"].format(alt_name=self.alt_name)
            self.caller.msg(response)
            raise InterruptCommand

    def _display_category(self):
        """
        Displays the table or tables for the specified category, showing the
        caller's settings.
        """
        table = self.settings.get_category(self.category_name).get_table()
        self.caller.msg(table)

    def _display_setting(self):
        """
        Displays the requested setting, its help_text, and current value.
        """
        category = self.settings.get_category(self.category_name)
        setting = category.get_setting(self.setting_name)

        table = EvTable(valign="t")
        table.add_row(setting.name, setting.help_text, str(setting.value))

        table.table[0].reformat(align="c")
        table.table[1].reformat(width=40)
        table.table[2].reformat(align="c")

        self.caller.msg(table)

    def _find(self):
        """
        Finds all settings with the given setting name and displays a table
        with the settings' names, categories, and help_text.
        """
        found_settings: List[SettingTuple] = []

        # For each model in our settings library, look for a field with
        # that setting's name.  If it exists, add it to the list.
        for category in self.settings.categories():
            found_settings.extend(
                setting
                for setting in category.settings()
                if self.setting_name in setting.name
            )

        if not found_settings:
            response = self.cmd_msgs["no_settings_found"].format(
                setting_name=self.setting_name
            )
            self.caller.msg(response)
            raise InterruptCommand

        find_table = EvTable(valign="t")

        for setting in found_settings:
            find_table.add_row(
                setting.name, setting.category, setting.help_text, str(setting.value)
            )

        # Last row has no padding at the bottom.
        for column in find_table.table:
            column.reformat(pad_bottom=1)
            column.reformat_cell(find_table.nrows - 1, pad_bottom=0)

        # Setting name and category are centered and top-aligned.
        # The help_text is just top (and left/default) aligned.
        find_table.table[0].reformat(align="c")
        find_table.table[1].reformat(align="c")
        find_table.table[2].reformat(width=40)
        find_table.table[3].reformat(align="c")

        response = self.cmd_msgs["find_results"].format(
            setting_name=self.setting_name, table=find_table
        )
        self.caller.msg(response)

    def _apply(self):
        """
        Applies the specified setting(s) to specified alt.
        """
        self.alt = self.caller.search(self.alt_name, global_search=True)

        # TODO: Verify this is necessary.
        if not self.alt:
            self.caller.msg("apply() - kaboom for finding the alt")
            raise InterruptCommand

        if self.setting_name:
            self._apply_setting()
        else:
            self._apply_category()

    def _apply_setting(self):
        """
        Applies one specific setting to an alt.
        """
        src_category = self.settings.get_category(self.category_name)
        alt_category = self.alt.settings.get_category(self.category_name)

        src_category.copy_one(alt_category, self.setting_name)

        caller_response = self.cmd_msgs["applied_setting"].format(
            category=self.category_name,
            setting_name=self.setting_name,
            alt_name=self.alt_name,
        )
        alt_response = self.cmd_msgs["alt_applied_setting"].format(
            category=self.category_name,
            setting_name=self.setting_name,
            alt_name=self.alt_name,
            value=self.alt.settings.get_setting_as_str(self.setting_name),
        )

        self.caller.msg(caller_response)
        self.alt.msg(alt_response)

    def _apply_category(self):
        """
        Applies all settings in the specified category to the alt.
        """
        # If we're applying a category, then we need to distinguish between
        # all and a specific category.  All means we iterate and copy each
        # category's settings.
        if self.category_name == "all":
            for src_settings, alt_settings in zip(
                self.settings.categories(), self.alt.settings.categories()
            ):
                src_settings.copy_to(alt_settings)
        else:
            src_settings = self.settings.get_category(self.category_name)
            alt_settings = self.alt.settings.get_category(self.category_name)

            src_settings.copy_to(alt_settings)

        caller_response = self.cmd_msgs["applied_category"].format(
            category=self.category_name, alt_name=self.alt_name
        )
        alt_response = self.cmd_msgs["alt_applied_category"].format(
            category=self.category_name, character=self.character
        )

        self.caller.msg(caller_response)
        self.alt.msg(alt_response)

    def _set_setting(self):
        """
        Sets the specified setting for the caller.
        """
        try:
            category = self.settings.get_category(self.category_name)
            category.set_setting(self.setting_name, self.rhs)
        except SettingsError as error:
            self.caller.msg(error)
            raise InterruptCommand

        response = self.cmd_msgs["setting_set"].format(
            category=self.category_name,
            setting_name=self.setting_name,
            setting_value=self.rhs,
        )
        self.caller.msg(response)
