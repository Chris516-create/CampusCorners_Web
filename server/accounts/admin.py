from django.conf import settings
from django.contrib import admin
from django.db.models import Count, Q

from .models import SavedEvent, User, UserOnboarding, UserPreferences


class CampusCornersAdminSite(admin.AdminSite):
    site_header = "Campus Corners · Data Center"
    site_title = "Campus Corners Admin"
    index_title = "Account data"
    index_template = "admin/index.html"

    def index(self, request, extra_context=None):
        accounts = User.objects.filter(is_staff=False)
        verified_ucla = accounts.filter(email_verified_at__isnull=False).filter(
            Q(email__endswith="@ucla.edu") | Q(email__endswith="@g.ucla.edu")
        )
        extra_context = dict(extra_context or {})
        extra_context.update(
            {
                "dashboard_environment": "Development database" if settings.DEBUG else "Configured database",
                "dashboard_stats": [
                    {"label": "Accounts", "value": accounts.count(), "detail": "Non-staff account records"},
                    {"label": "Verified UCLA", "value": verified_ucla.count(), "detail": "Verified mailbox on an allowed domain"},
                    {"label": "Saved events", "value": SavedEvent.objects.filter(user__is_staff=False).count(), "detail": "Current saved-event rows"},
                    {
                        "label": "Tour completed",
                        "value": UserOnboarding.objects.filter(user__is_staff=False, tour_status=UserOnboarding.TourStatus.COMPLETED).count(),
                        "detail": "Current onboarding state",
                    },
                ],
            }
        )
        return super().index(request, extra_context=extra_context)


site = CampusCornersAdminSite(name="admin")


class ReadOnlyAdmin(admin.ModelAdmin):
    actions = None
    list_per_page = 25

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        if not request.user.is_authenticated or not request.user.is_active or not request.user.is_staff:
            return False
        if request.user.is_superuser:
            return True
        permission = f"{self.opts.app_label}.view_{self.opts.model_name}"
        return request.user.has_perm(permission)


class VerifiedUCLAFilter(admin.SimpleListFilter):
    title = "Verified UCLA email"
    parameter_name = "verified_ucla"

    def lookups(self, request, model_admin):
        return (("yes", "Verified UCLA"), ("no", "Not verified"))

    def queryset(self, request, queryset):
        allowed_domains = Q(email__endswith="@ucla.edu") | Q(email__endswith="@g.ucla.edu")
        verified = Q(email_verified_at__isnull=False) & allowed_domains
        if self.value() == "yes":
            return queryset.filter(verified)
        if self.value() == "no":
            return queryset.filter(~verified)
        return queryset


class UserAdmin(ReadOnlyAdmin):
    fieldsets = (
        ("Profile", {"fields": ("id", "nickname", "profile_icon", "email")}),
        ("Account status", {"fields": ("is_active", "email_verified_at", "verified_ucla")}),
        ("Current product data", {"fields": ("saved_event_count", "onboarding_status")}),
        ("Dates", {"fields": ("created_at", "updated_at", "last_login")}),
    )
    readonly_fields = (
        "id", "nickname", "profile_icon", "email", "is_active", "email_verified_at",
        "verified_ucla", "saved_event_count", "onboarding_status", "created_at", "updated_at", "last_login",
    )
    list_display = ("nickname", "masked_email", "created_at", "verified_ucla", "saved_event_count", "onboarding_status")
    list_filter = (VerifiedUCLAFilter, "is_active", "created_at")
    search_fields = ("id", "nickname", "email")
    ordering = ("-created_at",)
    list_select_related = ("onboarding",)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_staff=False).annotate(
            _saved_event_count=Count("saved_events", distinct=True)
        ).select_related("onboarding")

    @admin.display(description="Email (masked)")
    def masked_email(self, obj):
        local, separator, domain = obj.email.partition("@")
        if not separator:
            return "Hidden"
        return f"{local[:1]}•••@{domain}"

    @admin.display(description="Verified UCLA", boolean=True)
    def verified_ucla(self, obj):
        return obj.is_verified_ucla

    @admin.display(description="Saved events", ordering="_saved_event_count")
    def saved_event_count(self, obj):
        return getattr(obj, "_saved_event_count", 0)

    @admin.display(description="Tour status")
    def onboarding_status(self, obj):
        try:
            return obj.onboarding.get_tour_status_display()
        except UserOnboarding.DoesNotExist:
            return "Not started"


class UserPreferencesAdmin(ReadOnlyAdmin):
    list_display = ("user", "promotional_email_opt_in", "promotional_email_opt_in_at", "promotional_email_revoked_at")
    search_fields = ("user__nickname", "user__email")
    list_filter = ("promotional_email_opt_in",)
    list_select_related = ("user",)
    readonly_fields = ("user", "promotional_email_opt_in", "promotional_email_opt_in_at", "promotional_email_revoked_at", "preference_copy_version")
    fields = readonly_fields


class UserOnboardingAdmin(ReadOnlyAdmin):
    list_display = ("user", "tour_status", "current_step", "updated_at", "first_completed_at")
    search_fields = ("user__nickname", "user__email")
    list_filter = ("tour_status", "updated_at")
    list_select_related = ("user",)
    readonly_fields = ("user", "version", "intro_seen", "tour_status", "current_step", "skipped_steps", "selected_tutorial_event_id", "updated_at", "first_completed_at")
    fields = readonly_fields


class SavedEventAdmin(ReadOnlyAdmin):
    list_display = ("user", "event_id", "saved_at")
    search_fields = ("user__nickname", "user__email", "event_id")
    list_filter = ("saved_at",)
    list_select_related = ("user",)
    readonly_fields = ("user", "event_id", "saved_at")
    fields = readonly_fields


site.register(User, UserAdmin)
site.register(UserPreferences, UserPreferencesAdmin)
site.register(UserOnboarding, UserOnboardingAdmin)
site.register(SavedEvent, SavedEventAdmin)
