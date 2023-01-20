from django.contrib import admin

from world.settings.models import (
    CommSettings,
    GeneralSettings,
    PlayerSettings,
    RPSettings,
)


class GeneralSettingsInline(admin.StackedInline):
    model = GeneralSettings
    exclude = ("base",)
    can_delete = False


class CommSettingsInline(admin.StackedInline):
    model = CommSettings
    exclude = ("base",)
    can_delete = False


class RPSettingsInline(admin.StackedInline):
    model = RPSettings
    exclude = ("base",)
    can_delete = False


class PlayerSettingsAdmin(admin.ModelAdmin):
    # readonly_fields = ("character",)
    inlines = [GeneralSettingsInline, CommSettingsInline, RPSettingsInline]


# Register your models here.
admin.site.register(PlayerSettings, PlayerSettingsAdmin)
admin.site.register(GeneralSettings)
admin.site.register(CommSettings)
admin.site.register(RPSettings)
