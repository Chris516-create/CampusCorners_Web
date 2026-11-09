import logging
from datetime import datetime, timezone as datetime_timezone

from django.contrib.auth import logout
from django.contrib.auth.models import AnonymousUser
from django.http import JsonResponse
from django.utils import timezone


logger = logging.getLogger(__name__)
IDLE_SECONDS = 7 * 24 * 60 * 60
ABSOLUTE_SECONDS = 30 * 24 * 60 * 60
PUBLIC_API_PATHS = {"/api/health", "/api/csrf", "/api/auth/register", "/api/auth/login"}


def session_times_are_valid(session, now=None):
    now = now or timezone.now()
    try:
        issued = datetime.fromisoformat(session["issued_at"])
        last_activity = datetime.fromisoformat(session["last_activity_at"])
        if issued.tzinfo is None or last_activity.tzinfo is None:
            return False
        now_utc = now.astimezone(datetime_timezone.utc)
        issued = issued.astimezone(datetime_timezone.utc)
        last_activity = last_activity.astimezone(datetime_timezone.utc)
        return (
            0 <= (now_utc - issued).total_seconds() < ABSOLUTE_SECONDS
            and 0 <= (now_utc - last_activity).total_seconds() < IDLE_SECONDS
        )
    except (KeyError, TypeError, ValueError):
        return False


class ApiErrorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception:
            if request.path_info.startswith("/api/"):
                logger.exception("Unhandled API request failure")
                response = JsonResponse(
                    {"error": {"code": "server_error", "message": "Something went wrong. Please try again."}},
                    status=500,
                )
                response["Cache-Control"] = "no-store"
                return response
            raise


class AccountSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        is_protected = path == "/api/auth/me" or path.startswith("/api/me/")
        if is_protected and request.session.get("_auth_user_id"):
            if not session_times_are_valid(request.session):
                logout(request)
                request.user = AnonymousUser()
                request.account_session_expired = True
        return self.get_response(request)
