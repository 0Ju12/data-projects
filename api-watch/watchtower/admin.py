from django.contrib import admin

from .models import CheckRun, DailyBrief, Incident, Target


@admin.register(Target)
class TargetAdmin(admin.ModelAdmin):
    list_display = ["name", "consecutive_failures", "last_success"]
    readonly_fields = ["slug", "spec", "baseline", "consecutive_failures", "last_success"]
    fields = readonly_fields + ["name"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CheckRun)
class CheckRunAdmin(admin.ModelAdmin):
    list_display = ["target", "checked_at", "status", "http_status", "duration_ms"]
    list_filter = ["target", "status"]
    readonly_fields = [f.name for f in CheckRun._meta.fields]

    def has_add_permission(self, r):
        return False

    def has_delete_permission(self, r, obj=None):
        return False


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ["target", "kind", "severity", "opened_at", "resolved_at"]
    readonly_fields = [f.name for f in Incident._meta.fields]

    def has_add_permission(self, r):
        return False

    def has_delete_permission(self, r, obj=None):
        return False


@admin.register(DailyBrief)
class BriefAdmin(admin.ModelAdmin):
    list_display = ["date", "item_id", "created_at"]
    readonly_fields = [f.name for f in DailyBrief._meta.fields]

    def has_add_permission(self, r):
        return False

    def has_delete_permission(self, r, obj=None):
        return False
