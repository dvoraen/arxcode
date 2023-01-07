"""
commands.base_commands.settings

This module defines the "settings" command and those related to the user experience.
"""


from collections import namedtuple

from evennia import EvTable, InterruptCommand

from commands.base import ArxCommand
from world.settings.models import ArxSettings, CommSettings, GeneralSettings, RPSettings


class CmdSettings(ArxCommand):
    """
    settings

    Manages your Arx gameplay settings.

    Syntax:
      settings <category>
      settings <category>/<setting_name>=<value>

      settings/find <setting_name>
      settings/apply <category>[/<setting_name>]=<character>

    Switches:
      (none) - displays the settings in the specified category
      /find  - returns the setting names, categories, and descriptions
               for settings containing the provided string
      /apply - applies the given category or setting to the given (alt)
               character

    Categories:
      all
      general - settings related to Arx gameplay
      comm    - settings related to communication (channels, pages, messages)
      rp      - settings related to RP

    Examples:
      settings all                     - shows all settings
      settings rp/emit_label=on        - sets emit_label in category "rp" to on
      settings/apply all=Alt           - applies every setting on you to Alt
      settings/apply rp/emit_label=Alt - applies emit_label setting to Alt
    """

    key = "settings"
    locks = "cmd:all()"
    help_category = "Settings"

    switch_options = ("find", "apply")

    model_map = {
        # This is a map between the command's categories and the models.
        # Largely used towards calling get() for the caller's settings data
        # as well as call model functions like SettingsModel.make_table().
        "all": ArxSettings,
        "general": GeneralSettings,
        "comm": CommSettings,
        "rp": RPSettings,
        # "craft": CraftSettings,
        # "bank": BankSettings,
    }

    # User input set by parse():
    category: str
    setting_name: str

    def parse(self):
        super().parse()

        self.category = None
        self.setting_name = None

        # If we're finding a setting, we "should" just have a setting_name
        # and that's all we need to do here.
        if "find" in self.switches:
            self.setting_name = self.args
            return

        # Parse lhs; it's the only "dynamic" part of the command that
        # needs attention.
        if "/" in self.lhs:
            self.category, self.setting_name = self.lhs.split("/", 1)
        else:
            self.category = self.lhs

    def func(self):
        if "find" in self.switches:
            self.find()
        elif "apply" in self.switches:
            self.apply()
        else:
            # If we have a setting name with a category, then user is
            # intending to set a setting.  Otherwise, just display
            # that category.
            if self.setting_name:
                self.set_setting()
            else:
                self.display()

    def validate_category(self):
        if self.category.lower() not in self.model_map.keys():
            self.caller.msg(f'"{self.category}" is not a valid settings category.')
            self.caller.msg("Valid categories: " + ", ".join(self.model_map.keys()))
            raise InterruptCommand

    def validate_setting(self):
        if self.category.lower() == "all":
            self.caller.msg(
                '"all" is not a valid category for setting a specific setting.'
            )
            self.caller.msg("Use settings/find to find that setting's category.")
            raise InterruptCommand

        # TODO: Look for the field in the given category's model.  If it doesn't exist, say so.

    def validate_alt(self):
        # TODO: Implement me.
        pass

    def display(self):
        """Displays the table for the specified settings category."""
        self.validate_category()

        table = self.model_map[self.category].get_table()
        self.caller.msg(table)

    def find(self):
        """
        Finds all settings with the given setting name and displays a table
        with the results, including category name.
        """

        FoundSetting = namedtuple("FoundSetting", ["name", "category", "help_text"])

        found_settings = []
        for category, model in self.model_map.items():
            # For each model in our settings library, look for a field with
            # that settings name.  If it exists, add it to the list.
            fields = model._meta.get_fields()

            found_settings = [
                FoundSetting(field.name, category, field.help_text)
                for field in fields
                if self.setting_name in field.name
            ]

        if not found_settings:
            self.caller.msg(
                f'No settings found with names containing "{self.setting_name}".'
            )
            return

        table = EvTable()

        for setting in found_settings:
            table.add_row(setting.name, setting.category, setting.help_text)

        table.table[0].reformat(align="c")
        table.table[1].reformat(align="c")

        self.caller.msg(table)

    def apply(self):
        """
        Applies specified setting(s) to specified alt, if that character IS
        the alt of the caller.
        """
        # Applying settings to an alt may require me to change my models such that
        # each category has a 1to1 to the owning character.  It would be easy to get
        # category settings for the alt, then, and perhaps with lower database interaction
        # than chaining through models to get to the required settings.
        self.validate_category()
        if self.setting_name:
            self.validate_setting()
        self.validate_alt()

    def set_setting(self):
        """
        Sets the specified setting for the caller, if it exists in that category.
        """
        self.validate_category()
        self.validate_setting()
