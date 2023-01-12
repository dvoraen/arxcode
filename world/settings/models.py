"""
settings.models

This file covers all the models (current and future) that are utilized by the
settings command.
"""


from django.core.exceptions import FieldDoesNotExist
from django.db import models
from evennia.utils.evtable import EvTable
from evennia.utils.idmapper.models import SharedMemoryModel

# TODO: use a RegexValidator for this
def validate_color(value):
    # TODO: This needs regex for foreground and background both.
    # bleh
    ansi_fg = r"[{|][rgybmcwxRGYBMCWX/-_*u]"
    ansi_bg = r"[{|]\[[rgybmcwx]"
    xterm256_fg = r"[{|][0-5]{3}|[{|]=[a-z]"
    xterm256_bg = r"[{|]\[[0-5]{3}|[{|]\[=[a-z]"


class CategorySettings(SharedMemoryModel):
    class Meta:
        abstract = True

    category = "Unknown"
    table_exclude = ()
    color_settings = ()

    def has_setting(self, setting_name):
        try:
            self._meta.get_field(setting_name)
            return True
        except FieldDoesNotExist:
            return False

    def get_setting_value(self, setting_name):
        value = getattr(self, setting_name)

        if isinstance(value, bool):
            return "On" if value else "Off"

        # TODO: This should be f"{value}{raw(value)}" but EvTable or ANSIString
        # is being weird about parsing ||.
        if setting_name in self.color_settings:
            return f"{value}Color"

        return value

    def get_table(self):
        fields = self._meta.get_fields()

        table = EvTable(
            f"|w{self.category}|n",
            border="tablecols",
            header_line_char="-",
            valign="t",
        )

        # Add to the table each field not specifically excluded from it.
        for field in fields:
            if field.name in self.table_exclude:
                continue

            value = self.get_setting_value(field.name)

            table.add_row(field.name, field.help_text, value)

        # Reformat table as follows:
        # - Settings names are centered.
        # - Setting descriptions are capped so there's no screen overflow.
        # - Setting values are centered.
        table.table[0].reformat(align="c")
        table.table[1].reformat(width=40)
        table.table[2].reformat(align="c")

        # - Column cells have a pad at the bottom except for the header and the
        #   last cell in each column.
        for column in table.table:
            column.reformat(pad_bottom=1)
            column.reformat_cell(0, pad_bottom=0)
            column.reformat_cell(table.nrows - 1, pad_bottom=0)

        return table


class PlayerSettings(CategorySettings):
    category = "All"

    class Meta:
        verbose_name = "Settings"
        verbose_name_plural = "Settings"

    character = models.OneToOneField(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="settings",
        db_index=True,
        primary_key=True,
    )

    # related models
    # general -> GeneralSettings
    # comm -> CommSettings
    # rp -> RPSettings
    # craft -> CraftSettings
    # bank -> BankSettings
    general: "GeneralSettings"
    comm: "CommSettings"
    rp: "RPSettings"
    # craft: "CraftSettings"
    # bank: "BankSettings"

    def get_table(self):
        all_table = EvTable(valign="t")

        category_models = [self.general, self.rp, self.comm]

        # This keeps track of which rows will have border_bottom=1.
        # Have to do it this way because EvTable will apply settings
        # a little oddly when using add_row(); putting kwargs in the
        # first row sets column-specific settings that can't be
        # overridden by reformat_cell().
        subheader_rows = []

        # For each category:
        # - Add a "category" row to all_table
        # - Add the rows of the category's columns to all_table
        for category_model in category_models:
            all_table.add_row(f"|w{category_model.category}", "", "")

            fields = category_model._meta.get_fields()

            for field in fields:
                if field.name in category_model.table_exclude:
                    continue
                value = category_model.get_setting_value(field.name)
                all_table.add_row(field.name, field.help_text, value)

            subheader_rows.append(all_table.nrows - 1)

        # Setting names and values are center-aligned.
        all_table.table[0].reformat(align="c", pad_bottom=1)
        all_table.table[1].reformat(width=40, pad_bottom=1)
        all_table.table[2].reformat(align="c", pad_bottom=1)

        # Format each "end of category" row to have no bottom padding
        # and a border at the bottom.
        for row in subheader_rows:
            for column in all_table.table:
                column.reformat_cell(row, pad_bottom=0, border_bottom=1)

        return all_table


class GeneralSettings(CategorySettings):
    class Meta:
        verbose_name = "General Settings"
        verbose_name_plural = "General Settings"

    category = "General"
    table_exclude = ("base",)

    base = models.OneToOneField(
        PlayerSettings,
        on_delete=models.CASCADE,
        editable=False,
        primary_key=True,
        related_name="general",
    )

    ### Settings for gameplay modes. ###

    brief_mode = models.BooleanField(
        help_text="Do not display room descs when moving through rooms.",
        default=False,
    )
    private_mode = models.BooleanField(
        help_text="Arx will not log pages sent to this character.\nNOTE: Staff may not be able to assist you with harassment if this mode is enabled.",
        default=False,
    )
    verbose_where_mode = models.BooleanField(
        help_text="Display roomtitle information on where.", default=False
    )
    ic_only_mode = models.BooleanField(
        help_text="Receive only IC forms of communication (emits, messages).\nNOTE: This will prevent you from receiving ANY pages and notifies the sender you are IC only.",
        default=False,
    )

    ### Settings for text removal. ###

    strip_ansi_names = models.BooleanField(
        help_text="Remove ANSI colors from text.", default=False
    )

    strip_ascii_text = models.BooleanField(
        help_text="Remove text contained in ASCII tags.", default=False
    )

    ### Settings for game emits. ###

    show_model_emits = models.BooleanField(
        help_text="Receive an emit when a character models what they're wearing.",
        default=True,
    )
    show_weather_emits = models.BooleanField(
        help_text="Receive an emit when the weather changes.", default=True
    )

    ## Settings for miscellany. ###

    # This setting (from @settings) applies only to messages sent to the ACCOUNT.
    # The tag is set on the account, so most times the setting won't apply.
    # As an example, spin up Local, turn this @settings on, and use @ooc.  Lots of newlines.
    apply_output_newline = models.BooleanField(
        help_text="Applies a newline character to the end of output sent by the game.",
        default=False,
    )


class CommSettings(CategorySettings):
    class Meta:
        verbose_name = "Comm Settings"
        verbose_name_plural = "Comm Settings"

    category = "Communication"
    table_exclude = ("base",)

    base = models.OneToOneField(
        PlayerSettings,
        on_delete=models.CASCADE,
        editable=False,
        primary_key=True,
        related_name="comm",
    )

    ### Settings for bboards. ###

    allow_bb_altread = models.BooleanField(
        help_text="Allow your alts to read your bboards.",
        default=False,
    )

    ### Settings for channels. ###

    highlight_chan_mention = models.BooleanField(
        help_text="Highlight your name when mentioned on a channel.", default=False
    )

    ### Settings for messengers. ###

    show_msg_text = models.BooleanField(
        help_text="Display the text of messages upon sending them.", default=False
    )
    show_msg_notice = models.BooleanField(
        help_text="Display the notification for pending messages.", default=True
    )
    show_msg_delivery = models.BooleanField(
        help_text="Display the notification for messenger deliveries.", default=True
    )


class RPSettings(CategorySettings):
    class Meta:
        verbose_name = "RP Settings"
        verbose_name_plural = "RP Settings"

    category = "RP"
    table_exclude = ("base",)
    color_settings = ("pose_quote_color", "pose_mention_color", "place_name_color")

    base = models.OneToOneField(
        PlayerSettings,
        on_delete=models.CASCADE,
        editable=False,
        primary_key=True,
        related_name="rp",
    )

    ### Settings for emits and poses. ###

    apply_emit_label = models.BooleanField(
        help_text="Apply a label naming the author of an emit at the start of it.",
        default=False,
    )
    apply_pose_break = models.BooleanField(
        help_text="Apply a newline between poses.",
        default=False,
    )

    ### Settings for highlight colors. ###

    pose_quote_color = models.CharField(
        help_text="The color to highlight text within pose quotation marks.",
        max_length=10,
        default="|n",
    )
    pose_mention_color = models.CharField(
        help_text="The color to highlight your name when mentioned in poses.",
        max_length=10,
        default="|n",
    )

    ### Settings for places. ###

    place_name_color = models.CharField(
        help_text="The color to highlight the place name when the TT command is used at your place.",
        max_length=10,
        default="|n",
    )


# class CraftSettings(CategorySettings):
#     category = "Crafting"
#     table_exclude = ("base",)

#     # TODO: Should I have ShopSettings with this in it?
#     # I think more db models need to exist before this is possible.  Namely:
#     # - DB listings of what a shop is
#     # - what room(s) comprise the shop
#     # - who owns the shop
#     # - the shop recipes, etc.
#     # shop_silver_minimum = models.PositiveIntegerField(
#     #     help_text="The minimum value of silver paid to a shop to generate an inform."
#     # )

#     def get_table(self):
#         table = super().get_table()

#         # TODO: Add the shop settings here.

#         return table


# class BankSettings(CategorySettings):
#     category = "Banking"
#     table_exclude = ("base",)

#     # related models
#     # resources -> Manager?[BankResourceSetting]
#     # materials -> Manager?[BankMaterialSetting]

#     def get_table(self):
#         table = super().get_table()

#         # TODO: Add the resources and materials here.

#         return table


# class BankResourceSetting(SharedMemoryModel):
#     bank_setting = models.ForeignKey(
#         BankSettings, on_delete=models.CASCADE, related_name="resources"
#     )

#     # resource = models.OneToOneField("", on_delete=models.CASCADE, related_name="+")
#     threshold = models.PositiveIntegerField(blank=False, default=0)


# class BankMaterialSetting(SharedMemoryModel):
#     bank_setting = models.ForeignKey(
#         BankSettings, on_delete=models.CASCADE, related_name="materials"
#     )

#     # material = models.OneToOneField("", on_delete=models.CASCADE, related_name="+")
#     threshold = models.PositiveIntegerField(blank=False, default=0)
