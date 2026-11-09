import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone as datetime_timezone
from functools import wraps
from pathlib import Path

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from .event_catalog import event_ids
from .limiters import (
    RateLimitExceeded,
    check_login_limits,
    clear_login_failures,
    count_registration,
    record_login_failure,
)
from .middleware import ABSOLUTE_SECONDS, IDLE_SECONDS
from .models import PROFILE_ICON_CHOICES, SavedEvent, User, UserOnboarding, UserPreferences, canonical_email


def error_response(code, message, status, fields=None, retry_after=None):
    body = {"error": {"code": code, "message": message}}
    if fields:
        body["error"]["fields"] = fields
    response = JsonResponse(body, status=status)
    response["Cache-Control"] = "no-store"
    if retry_after is not None:
        response["Retry-After"] = str(max(1, int(retry_after)))
    return response


def no_store(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        response = view(request, *args, **kwargs)
        response["Cache-Control"] = "private, no-store, max-age=0"
        response["Pragma"] = "no-cache"
        return response

    return wrapped


def json_body(request):
    if len(request.body) > 65536:
        raise ValueError("The request is too large.")
    try:
        value = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("Send a valid JSON object.")
    if not isinstance(value, dict):
        raise ValueError("Send a valid JSON object.")
    return value


def iso_now():
    return timezone.now().astimezone(datetime_timezone.utc).isoformat()


def start_user_session(request, user):
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    now = timezone.now().astimezone(datetime_timezone.utc)
    request.session["issued_at"] = now.isoformat()
    request.session["last_activity_at"] = now.isoformat()
    request.session.set_expiry(IDLE_SECONDS)


def touch_user_session(request):
    now = timezone.now().astimezone(datetime_timezone.utc)
    try:
        issued = datetime.fromisoformat(request.session["issued_at"])
    except (KeyError, TypeError, ValueError):
        return
    if issued.tzinfo is None:
        return
    issued = issued.astimezone(datetime_timezone.utc)
    expiry = min(now + timedelta(seconds=IDLE_SECONDS), issued + timedelta(seconds=ABSOLUTE_SECONDS))
    request.session["last_activity_at"] = now.isoformat()
    request.session.set_expiry(max(1, int((expiry - now).total_seconds())))


def get_user_for_request(request):
    if getattr(request, "account_session_expired", False):
        return None, error_response("session_expired", "Your session expired. Please log in again.", 401)
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_active:
        return None, error_response("unauthenticated", "Log in to continue.", 401)
    touch_user_session(request)
    return user, None


def ensure_account_rows(user):
    prefs, _ = UserPreferences.objects.get_or_create(user=user)
    onboarding, _ = UserOnboarding.objects.get_or_create(user=user)
    return prefs, onboarding


def safe_user_payload(user):
    prefs, onboarding = ensure_account_rows(user)
    return {
        "id": str(user.pk),
        "nickname": user.nickname,
        "profile_icon": user.profile_icon,
        "email": user.email,
        "ucla_email_claimed": user.ucla_email_claimed,
        "is_verified_ucla": user.is_verified_ucla,
        "email_verified_at": user.email_verified_at.isoformat() if user.email_verified_at else None,
        "preferences": {
            "promotional_email_opt_in": prefs.promotional_email_opt_in,
            "promotional_email_opt_in_at": (
                prefs.promotional_email_opt_in_at.isoformat() if prefs.promotional_email_opt_in_at else None
            ),
            "promotional_email_revoked_at": (
                prefs.promotional_email_revoked_at.isoformat() if prefs.promotional_email_revoked_at else None
            ),
            "preference_copy_version": prefs.preference_copy_version,
        },
        "onboarding": {
            "version": onboarding.version,
            "intro_seen": onboarding.intro_seen,
            "tour_status": onboarding.tour_status,
            "current_step": onboarding.current_step,
            "skipped_steps": onboarding.skipped_steps,
            "selected_tutorial_event_id": onboarding.selected_tutorial_event_id,
            "first_completed_at": onboarding.first_completed_at.isoformat() if onboarding.first_completed_at else None,
        },
    }


def _nick_errors(value):
    errors = []
    if not isinstance(value, str):
        return ["Enter a nickname."]
    nickname = value.strip()
    invalid = any(
        unicodedata.category(char) in {"Cc", "Cs", "Zl", "Zp"}
        or (unicodedata.category(char) == "Cf" and char not in {"\u200c", "\u200d"})
        for char in nickname
    )
    if not nickname or len(nickname) > 30 or invalid:
        errors.append("Use 1–30 characters without line breaks or control characters.")
    return errors


def _email_errors(value):
    if not isinstance(value, str):
        return ["Enter a valid email address."]
    email = canonical_email(value)
    if not email or len(email) > 254:
        return ["Enter a valid email address."]
    try:
        EmailValidator()(email)
    except ValidationError:
        return ["Enter a valid email address."]
    return []


def _registration_fields(data):
    fields = {}
    nickname = data.get("nickname")
    email = data.get("email")
    password = data.get("password")
    if _nick_errors(nickname):
        fields["nickname"] = _nick_errors(nickname)
    if _email_errors(email):
        fields["email"] = _email_errors(email)
    if not isinstance(password, str) or not (8 <= len(password) <= 128):
        fields["password"] = ["Use 8–128 characters."]
    elif password:
        try:
            from django.contrib.auth.password_validation import validate_password

            validate_password(password)
        except ValidationError as exc:
            fields["password"] = list(exc.messages)
    return fields


def _client_ip(request):
    return request.META.get("REMOTE_ADDR") or "unknown"


def _rate_limited(exc):
    return error_response(
        "rate_limited",
        "Too many attempts. Please wait and try again.",
        429,
        retry_after=exc.retry_after,
    )


@require_http_methods(["GET"])
@no_store
def health(request):
    return JsonResponse({"status": "ok"})


@require_http_methods(["GET"])
@ensure_csrf_cookie
@no_store
def csrf_bootstrap(request):
    return JsonResponse({"csrfToken": get_token(request)})


@require_http_methods(["POST"])
@no_store
def register(request):
    try:
        data = json_body(request)
    except ValueError as exc:
        return error_response("validation_error", str(exc), 400)
    try:
        count_registration(_client_ip(request))
    except RateLimitExceeded as exc:
        return _rate_limited(exc)

    fields = _registration_fields(data)
    if fields:
        return error_response("validation_error", "Check the fields and try again.", 400, fields)

    email = canonical_email(data["email"])
    nickname = data["nickname"].strip()
    try:
        with transaction.atomic():
            if User.objects.filter(email=email).exists():
                return error_response(
                    "email_in_use", "An account already uses that email address.", 409, {"email": ["Email is already in use."]}
                )
            user = User.objects.create_user(email=email, nickname=nickname, password=data["password"])
            UserPreferences.objects.create(user=user)
            UserOnboarding.objects.create(user=user)
    except IntegrityError:
        return error_response(
            "email_in_use", "An account already uses that email address.", 409, {"email": ["Email is already in use."]}
        )

    start_user_session(request, user)
    response = JsonResponse(
        {"user": safe_user_payload(user), "saved_event_ids": [], "csrfToken": get_token(request)},
        status=201,
    )
    return response


@require_http_methods(["POST"])
@no_store
def login_view(request):
    try:
        data = json_body(request)
    except ValueError as exc:
        return error_response("validation_error", str(exc), 400)
    raw_email = data.get("email")
    password = data.get("password")
    if not isinstance(raw_email, str) or not isinstance(password, str):
        return error_response("invalid_credentials", "Email or password is incorrect.", 401)
    email = canonical_email(raw_email)
    ip = _client_ip(request)
    try:
        check_login_limits(email or "invalid", ip)
    except RateLimitExceeded as exc:
        return _rate_limited(exc)

    user = authenticate(request, email=email, password=password)
    if not user or not user.is_active:
        try:
            record_login_failure(email or "invalid", ip)
        except RateLimitExceeded as exc:
            return _rate_limited(exc)
        return error_response("invalid_credentials", "Email or password is incorrect.", 401)

    clear_login_failures(email or "invalid", ip)
    start_user_session(request, user)
    saved = list(user.saved_events.order_by("saved_at").values_list("event_id", flat=True))
    return JsonResponse(
        {
            "user": safe_user_payload(user),
            "saved_event_ids": saved,
            "csrfToken": get_token(request),
        }
    )


@require_http_methods(["GET"])
@no_store
def me(request):
    user, failure = get_user_for_request(request)
    if failure:
        return failure
    saved = list(user.saved_events.order_by("saved_at").values_list("event_id", flat=True))
    return JsonResponse({"user": safe_user_payload(user), "saved_event_ids": saved})


@require_http_methods(["POST"])
@no_store
def logout_view(request):
    logout(request)
    return HttpResponse(status=204)


@require_http_methods(["PATCH"])
@no_store
def update_profile(request):
    user, failure = get_user_for_request(request)
    if failure:
        return failure
    try:
        data = json_body(request)
    except ValueError as exc:
        return error_response("validation_error", str(exc), 400)
    allowed_fields = {"nickname", "profile_icon"}
    if not data or set(data) - allowed_fields:
        return error_response(
            "validation_error",
            "Update only your nickname or profile icon.",
            400,
            {"nickname": ["Only the nickname or profile icon can be changed here."]},
        )

    fields = []
    if "nickname" in data:
        errors = _nick_errors(data.get("nickname"))
        if errors:
            return error_response("validation_error", "Check the nickname and try again.", 400, {"nickname": errors})
        user.nickname = data["nickname"].strip()
        fields.append("nickname")

    if "profile_icon" in data:
        profile_icon = data.get("profile_icon")
        valid_icons = {value for value, _label in PROFILE_ICON_CHOICES}
        if not isinstance(profile_icon, str) or profile_icon not in valid_icons:
            return error_response(
                "validation_error",
                "Choose an available profile icon.",
                400,
                {"profile_icon": ["Choose an available profile icon."]},
            )
        user.profile_icon = profile_icon
        fields.append("profile_icon")

    if fields:
        if "updated_at" not in fields:
            fields.append("updated_at")
        user.save(update_fields=fields)
    return JsonResponse({"user": safe_user_payload(user)})


@require_http_methods(["PATCH"])
@no_store
def update_preferences(request):
    user, failure = get_user_for_request(request)
    if failure:
        return failure
    try:
        data = json_body(request)
    except ValueError as exc:
        return error_response("validation_error", str(exc), 400)
    if set(data) != {"promotional_email_opt_in"} or not isinstance(
        data.get("promotional_email_opt_in"), bool
    ):
        return error_response(
            "validation_error",
            "Update only the promotional email preference.",
            400,
            {"promotional_email_opt_in": ["Choose yes or no."]},
        )

    prefs, _ = ensure_account_rows(user)
    selected = data["promotional_email_opt_in"]
    now = timezone.now()
    if selected and not prefs.promotional_email_opt_in:
        prefs.promotional_email_opt_in_at = now
    elif not selected and prefs.promotional_email_opt_in:
        prefs.promotional_email_revoked_at = now
    prefs.promotional_email_opt_in = selected
    prefs.preference_copy_version = "v1"
    prefs.save()
    return JsonResponse({"preferences": safe_user_payload(user)["preferences"]})


def _onboarding_payload(progress):
    return {
        "version": progress.version,
        "intro_seen": progress.intro_seen,
        "tour_status": progress.tour_status,
        "current_step": progress.current_step,
        "skipped_steps": progress.skipped_steps,
        "selected_tutorial_event_id": progress.selected_tutorial_event_id,
        "first_completed_at": progress.first_completed_at.isoformat() if progress.first_completed_at else None,
        "updated_at": progress.updated_at.isoformat(),
    }


@require_http_methods(["GET", "PUT"])
@no_store
def onboarding(request):
    user, failure = get_user_for_request(request)
    if failure:
        return failure
    progress, _ = UserOnboarding.objects.get_or_create(user=user)
    if request.method == "GET":
        return JsonResponse(_onboarding_payload(progress))
    try:
        data = json_body(request)
    except ValueError as exc:
        return error_response("validation_error", str(exc), 400)

    allowed = {
        "version",
        "intro_seen",
        "tour_status",
        "current_step",
        "skipped_steps",
        "selected_tutorial_event_id",
    }
    if set(data) - allowed:
        return error_response("validation_error", "Unsupported progress fields.", 400)
    fields = {}
    version = data.get("version", 1)
    if type(version) is not int or version != 1:
        fields["version"] = ["This onboarding version is not supported."]
    if "intro_seen" in data and not isinstance(data["intro_seen"], bool):
        fields["intro_seen"] = ["Choose true or false."]
    statuses = {choice for choice, _ in UserOnboarding.TourStatus.choices}
    if "tour_status" in data and (
        not isinstance(data["tour_status"], str) or data["tour_status"] not in statuses
    ):
        fields["tour_status"] = ["Choose a supported tour status."]
    if "current_step" in data and (
        not isinstance(data["current_step"], str) or data["current_step"] not in UserOnboarding.STEPS
    ):
        fields["current_step"] = ["Choose a supported tutorial step."]
    skipped = data.get("skipped_steps")
    if "skipped_steps" in data and (
        not isinstance(skipped, list)
        or any(step not in UserOnboarding.STEPS for step in skipped)
        or len(set(skipped)) != len(skipped)
    ):
        fields["skipped_steps"] = ["Use a list of distinct tutorial steps."]
    selected = data.get("selected_tutorial_event_id")
    if "selected_tutorial_event_id" in data and selected is not None:
        if not isinstance(selected, str) or selected not in event_ids():
            fields["selected_tutorial_event_id"] = ["Choose an event from the published sample."]
    if fields:
        return error_response("validation_error", "Check the progress fields and try again.", 400, fields)

    if "intro_seen" in data:
        progress.intro_seen = data["intro_seen"]
    if "current_step" in data:
        progress.current_step = data["current_step"]
    if "skipped_steps" in data:
        progress.skipped_steps = data["skipped_steps"]
    if "selected_tutorial_event_id" in data:
        progress.selected_tutorial_event_id = selected
    incoming_status = data.get("tour_status")
    if incoming_status and not (
        progress.first_completed_at and incoming_status != UserOnboarding.TourStatus.COMPLETED
    ):
        progress.tour_status = incoming_status
    if progress.tour_status == UserOnboarding.TourStatus.COMPLETED and not progress.first_completed_at:
        progress.first_completed_at = timezone.now()
    progress.version = 1
    progress.save()
    return JsonResponse(_onboarding_payload(progress))


@require_http_methods(["GET"])
@no_store
def saved_events(request):
    user, failure = get_user_for_request(request)
    if failure:
        return failure
    ids = list(user.saved_events.order_by("saved_at").values_list("event_id", flat=True))
    return JsonResponse({"event_ids": ids})


@require_http_methods(["PUT", "DELETE"])
@no_store
def saved_event(request, event_id):
    user, failure = get_user_for_request(request)
    if failure:
        return failure
    if event_id not in event_ids():
        return error_response("unknown_event", "That event is not in the published sample.", 404)
    if request.method == "PUT":
        record, _ = SavedEvent.objects.get_or_create(user=user, event_id=event_id)
        return JsonResponse({"event_id": record.event_id, "saved": True})
    SavedEvent.objects.filter(user=user, event_id=event_id).delete()
    return JsonResponse({"event_id": event_id, "saved": False})


@require_http_methods(["POST"])
@no_store
def import_saves(request):
    user, failure = get_user_for_request(request)
    if failure:
        return failure
    try:
        data = json_body(request)
    except ValueError as exc:
        return error_response("validation_error", str(exc), 400)
    ids = data.get("event_ids")
    if (
        set(data) != {"event_ids"}
        or not isinstance(ids, list)
        or len(ids) > 200
        or any(not isinstance(event_id, str) or len(event_id) > 128 for event_id in ids)
    ):
        return error_response("validation_error", "Choose up to 200 event IDs to import.", 400)
    known = event_ids()
    unique_ids = list(dict.fromkeys(ids))
    skipped = [event_id for event_id in unique_ids if event_id not in known]
    valid = [event_id for event_id in unique_ids if event_id in known]
    with transaction.atomic():
        present = set(
            user.saved_events.filter(event_id__in=valid).values_list("event_id", flat=True)
        )
        new_ids = [event_id for event_id in valid if event_id not in present]
        SavedEvent.objects.bulk_create(
            [SavedEvent(user=user, event_id=event_id) for event_id in new_ids],
            ignore_conflicts=True,
        )
    return JsonResponse({"imported": new_ids, "skipped": skipped})


@require_http_methods(["GET"])
def public_page(request, filename):
    allowed = {"index.html", "app.html", "about.html", "stickers.html", "404.html"}
    if filename in {"favicon.ico", "site.webmanifest"}:
        allowed.add(filename)
    if filename not in allowed:
        raise Http404
    path = Path(settings.BASE_DIR) / filename
    if not path.is_file():
        raise Http404
    return FileResponse(path.open("rb"), content_type="text/html; charset=utf-8" if filename.endswith(".html") else None)


def not_found(request, exception=None):
    if request.path_info.startswith("/api/"):
        return error_response("not_found", "The requested API endpoint was not found.", 404)
    try:
        response = public_page(request, "404.html")
        response.status_code = 404
        return response
    except Exception:
        return HttpResponse("Page not found.", status=404, content_type="text/plain; charset=utf-8")


def api_not_found(request, path=""):
    return error_response("not_found", "The requested API endpoint was not found.", 404)


def server_error(request):
    if request.path_info.startswith("/api/"):
        return error_response("server_error", "Something went wrong. Please try again.", 500)
    return HttpResponse("Something went wrong.", status=500, content_type="text/plain; charset=utf-8")


def csrf_failure(request, reason=""):
    if request.path_info.startswith("/api/"):
        return error_response("csrf_failed", "Refresh the page and try again.", 403)
    return HttpResponseForbidden("Security check failed.")
