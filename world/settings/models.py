"""
settings.models

This file covers all the models (current and future) that are utilized by the
settings command.
"""


from django.db import models
from evennia import EvTable
from evennia.utils.idmapper.models import SharedMemoryModel

# @settings/brief                           - general
# @settings/stripansinames                  - general?
# @settings/no_ascii                        - general
# @settings/ic_only                         - general
# @settings/ignore_weather                  - general
# @settings/private_mode                    - general?
# @settings/verbose_where                   - general
# @settings/ignore_model_emits              - general?

# @settings/bbaltread                       - comm
# @settings/ignore_bboard_notifications     - comm
# @settings/nomessengerpreview              - comm?
# @settings/ignore_messenger_notifications  - comm?
# @settings/ignore_messenger_deliveries     - comm?
# @settings/highlight_all_mentions          - comm

# @settings/emit_label                      - rp
# @settings/lrp                             - rp
# @settings/quote_color <color string>      - rp?
# @settings/name_color <color string>       - rp?
# @settings/posebreak                       - rp
# @settings/highlight_place_color           - rp

# @inform/shopminimum <number>              - craft

# @inform/bankminimum <type>,<number>       - bank

# TODO list
# @settings/newline_on_messages             - ???


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
    table_settings = {"border": "tablecols", "header_line_char": "-"}

    def get_table(self):
        fields = self._meta.get_fields()

        table = EvTable(self.category, **self.table_settings)

        # Checking for what fields to add by way of which ones have help_text
        # defined.  CraftSettings and BankSettings will be overriding get_table()
        # due to the nature of their settings.
        for field in fields:
            if field.help_text:
                table.add_row(field.name, field.help_text, getattr(self, field.name))

        # Reformat table as follows
        # - Column index 1 (setting description) needs to be wide.
        # - Row 0 of columns 1 and 2 (header row) have no borders to display the header row
        #   so that it looks like a "tab" sticking out of the top on the left.
        table.table[1].reformat_cell(0, border_width=0)
        table.table[2].reformat_cell(0, border_width=0)

        return table


class AllSettings(CategorySettings):
    category = "All"

    character = models.OneToOneField(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="settings",
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

    general = models.OneToOneField(
        "GeneralSettings", on_delete=models.CASCADE, related_name="+"
    )
    comm = models.OneToOneField(
        "CommSettings", on_delete=models.CASCADE, related_name="+"
    )
    rp = models.OneToOneField("RPSettings", on_delete=models.CASCADE, related_name="+")

    # craft = models.OneToOneField("CraftSettings", on_delete=models.CASCADE, related_name="+")
    # bank = models.OneToOneField("BankSettings", on_delete=models.CASCADE, related_name="+")

    def get_table(self):
        # Going to redo.  For displaying "all" settings, I want to have faux
        # subheaders for each category.  This seems to mean a separate row
        # with "subheader_settings" involved where the cells are basically borderless
        # except for perhaps the bottom.  (i.e., no top, left, right borders)

        # Example as shown to the caller:
        """
        +---------+
        | General |
        +---------+--------------------------------------+
        | setting | blahblabhlahblahblahblahblah | value |
        | setting | alskdjfasdhfakljdhflkasjdfhf | value |
        +------------------------------------------------+

        +---------+
        |   RP    |
        +---------+--------------------------------------+
        | setting | blahblabhlahblahblahblahblah | value |
        | setting | alskdjfasdhfakljdhflkasjdfhf | value |
        +------------------------------------------------+

        """
        # It might also mean "multiple tables".  We'll see.

        # I think what I want to do is this:
        # - make each category's subtable and stick in an iterable
        # - for each subtable, subtable.get() the rows
        # - rows.join() into one bigass str

        tables = []

        tables.append(self.general.get_table())
        tables.append(self.rp.get_table())
        tables.append(self.comm.get_table())

        return "\n".join(str(table) for table in tables)


class GeneralSettings(CategorySettings):
    category = "General"

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
    category = "Communication"

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
    category = "RP"

    class Meta:
        verbose_name = "rp settings"

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
