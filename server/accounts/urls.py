from django.urls import path

from . import api


urlpatterns = [
    path("health", api.health, name="health"),
    path("csrf", api.csrf_bootstrap, name="csrf"),
    path("auth/register", api.register, name="auth-register"),
    path("auth/login", api.login_view, name="auth-login"),
    path("auth/me", api.me, name="auth-me"),
    path("auth/logout", api.logout_view, name="auth-logout"),
    path("me/profile", api.update_profile, name="me-profile"),
    path("me/preferences", api.update_preferences, name="me-preferences"),
    path("me/onboarding", api.onboarding, name="me-onboarding"),
    path("me/saved-events", api.saved_events, name="me-saved-events"),
    path("me/saved-events/<str:event_id>", api.saved_event, name="me-saved-event"),
    path("me/import-saves", api.import_saves, name="me-import-saves"),
]
