from django.contrib import admin

from world.settings.models import (
    AccountSettings,
    CommSettings,
    GeneralSettings,
    CharacterSettings,
    RPSettings,
)


class AccountSettingsInline(admin.StackedInline):
    model = AccountSettings
    readonly_fields = ("account", "owner")
    can_delete = False


class GeneralSettingsInline(admin.StackedInline):
    model = GeneralSettings
    readonly_fields = ("owner",)
    can_delete = False


class CommSettingsInline(admin.StackedInline):
    model = CommSettings
    readonly_fields = ("owner",)
    can_delete = False


class RPSettingsInline(admin.StackedInline):
    model = RPSettings
    readonly_fields = ("owner",)
    can_delete = False


class AccountSettingsAdmin(admin.ModelAdmin):
    readonly_fields = ("account",)


class CharacterSettingsAdmin(admin.ModelAdmin):
    readonly_fields = ("character",)
    inlines = [
        AccountSettingsInline,
        GeneralSettingsInline,
        CommSettingsInline,
        RPSettingsInline,
    ]


# Register your models here.
admin.site.register(CharacterSettings, CharacterSettingsAdmin)
admin.site.register(AccountSettings, AccountSettingsAdmin)
admin.site.register(GeneralSettings)
admin.site.register(CommSettings)
admin.site.register(RPSettings)
