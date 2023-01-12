from django.contrib import admin

from world.settings.models import (
    PlayerSettings,
    CommSettings,
    GeneralSettings,
    RPSettings,
)


class GeneralSettingsInline(admin.StackedInline):
    model = GeneralSettings
    can_delete = False


class CommSettingsInline(admin.StackedInline):
    model = CommSettings
    can_delete = False


class RPSettingsInline(admin.StackedInline):
    model = RPSettings
    can_delete = False


class PlayerSettingsAdmin(admin.ModelAdmin):
    # readonly_fields = ("character",)
    inlines = [GeneralSettingsInline, CommSettingsInline, RPSettingsInline]


# Register your models here.
admin.site.register(PlayerSettings, PlayerSettingsAdmin)
admin.site.register(GeneralSettings)
admin.site.register(CommSettings)
admin.site.register(RPSettings)
