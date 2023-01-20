from django.contrib import admin

from world.settings.models import (
    CommSettings,
    GeneralSettings,
    PlayerSettings,
    RPSettings,
)


class GeneralSettingsInline(admin.StackedInline):
    model = GeneralSettings
    readonly_fields = ("base",)
    can_delete = False


class CommSettingsInline(admin.StackedInline):
    model = CommSettings
    readonly_fields = ("base",)
    can_delete = False


class RPSettingsInline(admin.StackedInline):
    model = RPSettings
    readonly_fields = ("base",)
    can_delete = False


class PlayerSettingsAdmin(admin.ModelAdmin):
    readonly_fields = ("character",)
    inlines = [GeneralSettingsInline, CommSettingsInline, RPSettingsInline]


# Register your models here.
admin.site.register(PlayerSettings, PlayerSettingsAdmin)
admin.site.register(GeneralSettings)
admin.site.register(CommSettings)
admin.site.register(RPSettings)
