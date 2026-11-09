import json
from datetime import datetime, timedelta

from django.contrib.auth.hashers import identify_hasher
from django.test import Client, TestCase
from django.utils import timezone

from .event_catalog import event_ids
from .models import AuthRateBucket, SavedEvent, User, UserOnboarding, UserPreferences


PASSWORD = "this is a safe test phrase 42"
SAMPLE_EVENT = "ig-aca-workshop-miyazaki"


def post_json(client, path, data, **headers):
    return client.post(path, data=json.dumps(data), content_type="application/json", **headers)


class AuthApiTests(TestCase):
    def setUp(self):
        self.client = Client()

    def register(self, email="rain@example.com", nickname="Rain", password=PASSWORD, **headers):
        return post_json(
            self.client,
            "/api/auth/register",
            {"nickname": nickname, "email": email, "password": password},
            **headers,
        )

    def login(self, email="rain@example.com", password=PASSWORD, **headers):
        return post_json(
            self.client,
            "/api/auth/login",
            {"email": email, "password": password},
            **headers,
        )

    def test_register_normalizes_email_and_returns_only_safe_profile(self):
        response = self.register(email=" Rain+tag@Example.COM ", nickname="吱吱 🐾")
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        user = payload["user"]
        self.assertEqual(user["email"], "rain+tag@example.com")
        self.assertEqual(user["nickname"], "吱吱 🐾")
        self.assertEqual(user["profile_icon"], "sparko")
        self.assertFalse(user["ucla_email_claimed"])
        self.assertFalse(user["is_verified_ucla"])
        self.assertNotIn("password", user)
        self.assertNotIn("session_key", payload)
        self.assertEqual(response.cookies["cc_session"]["httponly"], True)
        self.assertTrue(UserPreferences.objects.get(user__email=user["email"]).promotional_email_opt_in is False)
        self.assertEqual(UserOnboarding.objects.get(user__email=user["email"]).version, 1)

    def test_casefolded_duplicate_email_is_rejected(self):
        self.assertEqual(self.register(email="Rain+tag@Example.com").status_code, 201)
        response = self.register(email="rain+TAG@example.COM")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "email_in_use")
        self.assertEqual(User.objects.count(), 1)

    def test_registration_validates_nickname_password_and_email(self):
        response = self.register(nickname="bad\nname", password="short")
        self.assertEqual(response.status_code, 400)
        self.assertIn("nickname", response.json()["error"]["fields"])
        self.assertIn("password", response.json()["error"]["fields"])
        response = self.register(email="not-an-email")
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json()["error"]["fields"])

    def test_password_uses_argon2_and_is_not_returned(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="rain@example.com")
        self.assertEqual(identify_hasher(user.password).algorithm, "argon2")
        self.assertNotIn(user.password, response.content.decode("utf-8"))

    def test_login_uses_generic_invalid_credentials_response(self):
        self.register()
        wrong = self.login(password="wrong password")
        missing = self.login(email="missing@example.com", password=PASSWORD)
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(wrong.json(), missing.json())
        self.assertEqual(wrong.json()["error"]["code"], "invalid_credentials")

    def test_exact_ucla_domains_are_claims_but_never_verified_without_timestamp(self):
        for email, claimed in [
            ("one@ucla.edu", True),
            ("two@g.ucla.edu", True),
            ("three@ucla.edu.example.com", False),
            ("four@notucla.edu", False),
        ]:
            user = User.objects.create_user(email=email, nickname="Test", password=PASSWORD)
            self.assertEqual(user.ucla_email_claimed, claimed)
            self.assertFalse(user.is_verified_ucla)
            self.assertIsNone(user.email_verified_at)
            user.email_verified_at = timezone.now()
            user.save(update_fields=["email_verified_at"])
            self.assertEqual(user.is_verified_ucla, claimed)

    def test_preferences_record_opt_in_and_revocation_without_email_delivery(self):
        self.register()
        csrf = self.client.get("/api/csrf").json()["csrfToken"]
        enabled = self.client.patch(
            "/api/me/preferences",
            data=json.dumps({"promotional_email_opt_in": True}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(enabled.status_code, 200)
        prefs = UserPreferences.objects.get(user__email="rain@example.com")
        self.assertTrue(prefs.promotional_email_opt_in)
        self.assertIsNotNone(prefs.promotional_email_opt_in_at)
        disabled = self.client.patch(
            "/api/me/preferences",
            data=json.dumps({"promotional_email_opt_in": False}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(disabled.status_code, 200)
        prefs.refresh_from_db()
        self.assertFalse(prefs.promotional_email_opt_in)
        self.assertIsNotNone(prefs.promotional_email_revoked_at)


class CsrfAndSessionTests(TestCase):
    def test_csrf_is_required_for_account_creation_and_bootstrap_returns_token(self):
        client = Client(enforce_csrf_checks=True)
        data = {"nickname": "Rain", "email": "rain@example.com", "password": PASSWORD}
        rejected = post_json(client, "/api/auth/register", data)
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(rejected.json()["error"]["code"], "csrf_failed")
        token = client.get("/api/csrf").json()["csrfToken"]
        accepted = post_json(client, "/api/auth/register", data, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(accepted.status_code, 201)
        self.assertIn("csrfToken", accepted.json())

    def test_session_survives_restore_and_activity_renews_idle_window(self):
        client = Client()
        post_json(client, "/api/auth/register", {"nickname": "Rain", "email": "rain@example.com", "password": PASSWORD})
        session = client.session
        issued = session["issued_at"]
        session["last_activity_at"] = (timezone.now() - timedelta(days=6)).isoformat()
        session.save()
        response = client.get("/api/auth/me")
        self.assertEqual(response.status_code, 200)
        renewed = client.session
        self.assertEqual(renewed["issued_at"], issued)
        self.assertGreater(datetime.fromisoformat(renewed["last_activity_at"]), timezone.now() - timedelta(minutes=1))

    def test_idle_and_absolute_expiry_clear_authentication(self):
        for field, age in [("last_activity_at", timedelta(days=8)), ("issued_at", timedelta(days=31))]:
            client = Client()
            post_json(client, "/api/auth/register", {"nickname": "Rain", "email": f"{field}@example.com", "password": PASSWORD})
            session = client.session
            session[field] = (timezone.now() - age).isoformat()
            session.save()
            response = client.get("/api/auth/me")
            self.assertEqual(response.status_code, 401)
            self.assertNotIn("_auth_user_id", client.session)

    def test_logout_invalidates_a_replayed_cookie(self):
        client = Client()
        post_json(client, "/api/auth/register", {"nickname": "Rain", "email": "rain@example.com", "password": PASSWORD})
        old_cookie = client.cookies["cc_session"].value
        self.assertEqual(client.post("/api/auth/logout").status_code, 204)
        client.cookies["cc_session"] = old_cookie
        self.assertEqual(client.get("/api/auth/me").status_code, 401)

    def test_login_throttle_returns_retry_timing_after_five_failures(self):
        client = Client()
        post_json(client, "/api/auth/register", {"nickname": "Rain", "email": "rain@example.com", "password": PASSWORD})
        for _ in range(5):
            response = post_json(client, "/api/auth/login", {"email": "rain@example.com", "password": "incorrect"})
            self.assertEqual(response.status_code, 401)
        blocked = post_json(client, "/api/auth/login", {"email": "rain@example.com", "password": PASSWORD})
        self.assertEqual(blocked.status_code, 429)
        self.assertGreater(int(blocked["Retry-After"]), 0)
        self.assertEqual(AuthRateBucket.objects.filter(operation="login_email").count(), 1)


class ProtectedApiTests(TestCase):
    def make_client(self, email):
        client = Client()
        response = post_json(
            client,
            "/api/auth/register",
            {"nickname": email.split("@")[0], "email": email, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 201)
        return client

    def test_saved_events_are_isolated_and_idempotent(self):
        first = self.make_client("first@example.com")
        second = self.make_client("second@example.com")
        self.assertEqual(first.put(f"/api/me/saved-events/{SAMPLE_EVENT}").status_code, 200)
        self.assertEqual(first.put(f"/api/me/saved-events/{SAMPLE_EVENT}").status_code, 200)
        self.assertEqual(first.get("/api/me/saved-events").json()["event_ids"], [SAMPLE_EVENT])
        self.assertEqual(second.get("/api/me/saved-events").json()["event_ids"], [])
        self.assertEqual(SavedEvent.objects.count(), 1)
        first.delete(f"/api/me/saved-events/{SAMPLE_EVENT}")
        self.assertEqual(first.get("/api/me/saved-events").json()["event_ids"], [])

    def test_event_ids_are_read_from_the_embedded_json_and_unknown_ids_are_rejected(self):
        self.assertIn(SAMPLE_EVENT, event_ids())
        self.assertEqual(self.make_client("rain@example.com").put("/api/me/saved-events/not-a-real-event").status_code, 404)

    def test_import_is_explicit_deduplicated_and_reports_unknown_ids(self):
        client = self.make_client("rain@example.com")
        response = post_json(
            client,
            "/api/me/import-saves",
            {"event_ids": [SAMPLE_EVENT, SAMPLE_EVENT, "missing-event"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"imported": [SAMPLE_EVENT], "skipped": ["missing-event"]})

    def test_onboarding_validates_states_and_completed_progress_does_not_regress(self):
        client = self.make_client("rain@example.com")
        completed = client.put(
            "/api/me/onboarding",
            data=json.dumps({"tour_status": "completed", "current_step": "route", "selected_tutorial_event_id": SAMPLE_EVENT}),
            content_type="application/json",
        )
        self.assertEqual(completed.status_code, 200)
        regressed = client.put(
            "/api/me/onboarding",
            data=json.dumps({"tour_status": "in_progress", "current_step": "filter"}),
            content_type="application/json",
        )
        self.assertEqual(regressed.status_code, 200)
        self.assertEqual(regressed.json()["tour_status"], "completed")
        invalid = client.put(
            "/api/me/onboarding",
            data=json.dumps({"tour_status": "made_up"}),
            content_type="application/json",
        )
        self.assertEqual(invalid.status_code, 400)
        for malformed in ({"tour_status": []}, {"current_step": {}}, {"version": True}, {"skipped_steps": [{}]}):
            response = client.put(
                "/api/me/onboarding",
                data=json.dumps(malformed),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 400)

    def test_public_files_are_allowlisted_and_api_404_is_json(self):
        client = Client()
        self.assertEqual(client.get("/app.html").status_code, 200)
        self.assertEqual(client.get("/app/app.js").status_code, 200)
        self.assertEqual(client.get("/server/manage.py").status_code, 404)
        self.assertEqual(client.get("/api/not-a-route").json()["error"]["code"], "not_found")

    def test_health_is_minimal(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class ProfileApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        response = post_json(
            self.client,
            "/api/auth/register",
            {"nickname": "Rain", "email": "rain@example.com", "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 201)
        self.user = User.objects.get(email="rain@example.com")

    def patch(self, data, client=None, csrf=None):
        headers = {"HTTP_X_CSRFTOKEN": csrf} if csrf else {}
        return (client or self.client).patch(
            "/api/me/profile",
            data=json.dumps(data),
            content_type="application/json",
            **headers,
        )

    def test_unicode_nickname_is_saved_and_only_safe_profile_data_is_returned(self):
        saved = SavedEvent.objects.create(user=self.user, event_id=SAMPLE_EVENT)
        prefs = UserPreferences.objects.get(user=self.user)
        prefs.promotional_email_opt_in = True
        prefs.save(update_fields=["promotional_email_opt_in"])
        verified_at = timezone.now()
        self.user.email_verified_at = verified_at
        self.user.save(update_fields=["email_verified_at"])

        response = self.patch({"nickname": "  小星星 🐾  "})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user"]["nickname"], "小星星 🐾")
        self.assertEqual(payload["user"]["email"], "rain@example.com")
        self.assertFalse(payload["user"]["is_verified_ucla"])
        self.assertNotIn("password", response.content.decode("utf-8"))
        self.assertNotIn(self.user.password, response.content.decode("utf-8"))
        self.assertNotIn("session_key", response.content.decode("utf-8"))
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.nickname, "小星星 🐾")
        self.assertEqual(SavedEvent.objects.get(pk=saved.pk).event_id, SAMPLE_EVENT)
        prefs.refresh_from_db()
        self.assertTrue(prefs.promotional_email_opt_in)
        self.assertEqual(self.user.email_verified_at, verified_at)

    def test_profile_icon_is_a_persisted_allowlisted_key(self):
        self.assertEqual(self.user.profile_icon, "sparko")
        for profile_icon in ("sparko", "sparkle", "flower", "heart"):
            with self.subTest(profile_icon=profile_icon):
                response = self.patch({"profile_icon": profile_icon})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["user"]["profile_icon"], profile_icon)
                self.user.refresh_from_db()
                self.assertEqual(self.user.profile_icon, profile_icon)

        for value in ("custom-upload", "https://example.com/avatar.png", None):
            with self.subTest(profile_icon=value):
                rejected = self.patch({"profile_icon": value})
                self.assertEqual(rejected.status_code, 400)
                self.assertIn("profile_icon", rejected.json()["error"]["fields"])

        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_icon, "heart")

    def test_profile_edit_refreshes_database_timestamp(self):
        previous = timezone.now() - timedelta(hours=1)
        User.objects.filter(pk=self.user.pk).update(updated_at=previous)
        response = self.patch({"profile_icon": "flower"})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertGreater(self.user.updated_at, previous)

    def test_empty_overlong_and_control_character_nicknames_are_rejected(self):
        for nickname in ("", "   ", "x" * 31, "bad\nname", "bad\u2028name"):
            with self.subTest(nickname=repr(nickname)):
                response = self.patch({"nickname": nickname})
                self.assertEqual(response.status_code, 400)
                self.assertIn("nickname", response.json()["error"]["fields"])
                self.user.refresh_from_db()
                self.assertEqual(self.user.nickname, "Rain")

    def test_duplicate_nicknames_are_allowed(self):
        User.objects.create_user(email="other@example.com", nickname="Same", password=PASSWORD)
        response = self.patch({"nickname": "Same"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(nickname="Same").count(), 2)

    def test_guest_and_expired_sessions_cannot_edit_profile(self):
        guest = Client()
        self.assertEqual(self.patch({"nickname": "Guest"}, client=guest).status_code, 401)
        session = self.client.session
        session["last_activity_at"] = (timezone.now() - timedelta(days=8)).isoformat()
        session.save()
        response = self.patch({"nickname": "Expired"})
        self.assertEqual(response.status_code, 401)
        self.user.refresh_from_db()
        self.assertEqual(self.user.nickname, "Rain")

    def test_csrf_and_exact_field_allowlist_are_enforced(self):
        client = Client(enforce_csrf_checks=True)
        csrf = client.get("/api/csrf").json()["csrfToken"]
        registered = post_json(
            client,
            "/api/auth/register",
            {"nickname": "Rain", "email": "csrf@example.com", "password": PASSWORD},
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(registered.status_code, 201)
        csrf = registered.json()["csrfToken"]
        rejected = self.patch({"nickname": "No CSRF"}, client=client)
        self.assertEqual(rejected.status_code, 403)
        accepted = self.patch({"nickname": "With CSRF"}, client=client, csrf=csrf)
        self.assertEqual(accepted.status_code, 200)

        for extra in (
            {"email": "attacker@example.com"},
            {"password": "new password"},
            {"id": str(self.user.pk)},
            {"user_id": str(self.user.pk)},
            {"is_staff": True},
            {"email_verified_at": timezone.now().isoformat()},
            {"is_verified_ucla": True},
        ):
            with self.subTest(extra=extra):
                response = self.patch({"nickname": "Attempt", **extra})
                self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.nickname, "Rain")
        self.assertEqual(self.user.email, "rain@example.com")


class AdminViewerTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            email="member@example.com", nickname="Member", password=PASSWORD
        )
        UserPreferences.objects.create(user=self.member)
        UserOnboarding.objects.create(user=self.member)
        SavedEvent.objects.create(user=self.member, event_id=SAMPLE_EVENT)

    def test_regular_account_cannot_open_staff_data_center(self):
        self.client.force_login(self.member)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_can_read_dashboard_and_masked_account_list(self):
        staff = User.objects.create_superuser(
            email="operator@example.com", nickname="Operator", password=PASSWORD
        )
        self.client.force_login(staff)

        dashboard = self.client.get("/admin/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Campus Corners")
        self.assertContains(dashboard, "Read only")
        self.assertContains(dashboard, "Saved events")

        listing = self.client.get("/admin/accounts/user/")
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "m•••@example.com")
        self.assertNotContains(listing, "member@example.com")
        self.assertNotContains(listing, self.member.password)

    def test_authorized_account_detail_is_read_only_and_never_shows_password_hash(self):
        staff = User.objects.create_superuser(
            email="operator@example.com", nickname="Operator", password=PASSWORD
        )
        self.client.force_login(staff)

        detail = self.client.get(f"/admin/accounts/user/{self.member.pk}/change/")
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "member@example.com")
        self.assertContains(detail, "profile_icon")
        self.assertNotContains(detail, self.member.password)
        self.assertNotContains(detail, "Save and continue editing")

        add = self.client.get("/admin/accounts/user/add/")
        delete = self.client.get(f"/admin/accounts/user/{self.member.pk}/delete/")
        self.assertEqual(add.status_code, 403)
        self.assertEqual(delete.status_code, 403)
