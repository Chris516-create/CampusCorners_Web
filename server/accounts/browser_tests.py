import os
import json
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


SERVER_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = SERVER_DIR.parent


class CampusCornersBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temp = tempfile.TemporaryDirectory(prefix="campus-corners-browser-")
        temp_path = Path(cls.temp.name)
        cls.log_file = (temp_path / "django.log").open("w+")
        cls.env = os.environ.copy()
        cls.env.update(
            {
                "DJANGO_DEBUG": "true",
                "DJANGO_SECRET_KEY": "browser-test-only-secret-key",
                "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
                "DATABASE_URL": "",
                "DJANGO_SQLITE_NAME": str(temp_path / "browser-tests.sqlite3"),
            }
        )
        cls.python = sys.executable
        subprocess.run(
            [cls.python, str(SERVER_DIR / "manage.py"), "migrate", "--noinput"],
            cwd=REPO_DIR,
            env=cls.env,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.server = subprocess.Popen(
            [cls.python, str(SERVER_DIR / "manage.py"), "runserver", f"127.0.0.1:{cls.port}", "--noreload"],
            cwd=REPO_DIR,
            env=cls.env,
            stdout=cls.log_file,
            stderr=subprocess.STDOUT,
        )
        for _ in range(100):
            if cls.server.poll() is not None:
                raise RuntimeError("The temporary preview server exited:\n" + (temp_path / "django.log").read_text())
            try:
                with urllib.request.urlopen(cls.base_url + "/api/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.1)
        else:
            raise RuntimeError("The temporary preview server did not become ready.")
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "browser"):
            cls.browser.close()
        if hasattr(cls, "playwright"):
            cls.playwright.stop()
        if hasattr(cls, "server"):
            cls.server.terminate()
            cls.server.wait(timeout=10)
        if hasattr(cls, "log_file"):
            cls.log_file.close()
        if hasattr(cls, "temp"):
            cls.temp.cleanup()
        super().tearDownClass()

    def setUp(self):
        self.context = self.browser.new_context(
            viewport={"width": 390, "height": 844},
            reduced_motion="reduce",
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(7000)
        self.page_errors = []
        self.page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        response = self.page.goto(self.base_url + "/app.html", wait_until="domcontentloaded")
        self.assertEqual(response.status, 200)
        expect(self.page.locator("#ccModalRoot")).to_be_visible()

    def tearDown(self):
        self.context.close()

    def advance_intro_to_invitation(self):
        self.page.get_by_role("button", name="Meet the map").click()
        self.page.get_by_role("button", name="Next").click()

    def start_guest_tour(self):
        self.advance_intro_to_invitation()
        self.page.get_by_role("button", name="Continue as guest").click()
        expect(self.page.locator("#ccTourLayer")).to_be_visible()

    def open_highlighted_event(self):
        target = self.page.locator(".pin.cc-tour-highlight")
        if target.count() == 0:
            sample = self.page.get_by_role("button", name="Use a sample event")
            if sample.count() and sample.is_visible():
                sample.click()
        if target.count() == 0:
            self.fail(
                "No event pin is highlighted. Tour card: "
                + self.page.locator("#ccTourCard").inner_text()
                + "; browser errors: "
                + repr(self.page_errors)
            )
        target.click()

    def test_guest_can_complete_responsive_tour_and_save_a_sample_event(self):
        self.assertTrue(
            self.page.locator(".cc-intro-sparko").evaluate("image => image.currentSrc.endsWith('sparko-idle.png')")
        )
        self.start_guest_tour()
        self.assert_tour_guide_visible()

        app_box = self.page.locator("#app").bounding_box()
        card_box = self.page.locator("#ccTourCard").bounding_box()
        self.assertIsNotNone(app_box)
        self.assertIsNotNone(card_box)
        self.assertGreaterEqual(card_box["x"], app_box["x"])
        self.assertGreaterEqual(card_box["y"], app_box["y"])
        self.assertLessEqual(card_box["x"] + card_box["width"], app_box["x"] + app_box["width"] + 1)
        self.assertLessEqual(card_box["y"] + card_box["height"], app_box["y"] + app_box["height"] + 1)

        self.page.locator('[data-tour="category-arts"]').click()
        self.assert_tour_guide_visible()
        next_button = self.page.locator(".cc-tour-next")
        expect(next_button).to_be_enabled()
        next_button.click()

        self.open_highlighted_event()
        expect(self.page.locator("#sheetTitle")).to_be_visible()
        self.assert_tour_guide_visible()
        self.page.locator(".cc-tour-next").click()
        self.assert_tour_guide_visible()
        self.page.locator('[data-tour="event-save"]').click()
        expect(self.page.locator(".cc-tour-next")).to_be_enabled()
        self.page.get_by_role("button", name="Show My Events").click()
        expect(self.page.locator("#mine")).to_be_visible()
        self.page.get_by_role("button", name="Back to event").click()
        self.page.locator(".cc-tour-next").click()
        self.assert_tour_guide_visible()
        self.page.locator('[data-tour="event-route"]').click()
        expect(self.page.locator("#routebar")).to_be_visible()
        self.page.get_by_role("button", name="Finish").click()

        expect(self.page.locator("#ccTourLayer")).to_be_hidden()
        progress = self.page.evaluate("JSON.parse(localStorage.getItem('cc:onboarding:v1'))")
        self.assertEqual(progress["tour_status"], "completed")
        self.assertTrue(self.page.evaluate("localStorage.getItem('cc:guest:v1') !== null"))
        self.assertEqual(self.page_errors, [])

    def assert_tour_guide_visible(self):
        expect(self.page.locator(".cc-tour-sparko")).to_be_visible()
        expect(self.page.locator(".cc-tour-tail")).to_be_visible()
        self.assertEqual(
            self.page.locator(".cc-tour-sparko").evaluate("image => getComputedStyle(image).animationName"),
            "none",
        )

    def test_home_explore_opens_map_with_guest_login_dialog(self):
        self.page.goto(self.base_url + "/", wait_until="domcontentloaded")
        account_link = self.page.locator("#siteAccount")
        expect(account_link.locator("img")).to_have_attribute("src", re.compile(r"profile-guest\.svg$"))
        expect(account_link).to_have_attribute("href", "app.html#account")
        self.page.get_by_role("link", name="Explore the map").click()

        expect(self.page).to_have_url(re.compile(r"/app\.html#map$"))
        expect(self.page.locator("#account")).to_be_hidden()
        expect(self.page.get_by_role("dialog", name="Log in")).to_be_visible()
        expect(self.page.locator(".cc-auth-form")).to_contain_text("Continue as guest")
        expect(self.page.locator("#tSet")).to_contain_text("Settings")
        expect(self.page.locator("#tSet")).to_have_attribute("aria-current", "false")
        expect(self.page.locator("#tAccount")).to_be_visible()
        expect(self.page.locator("#tAccount .cc-account-fab-avatar img")).to_have_attribute("src", re.compile(r"profile-guest\.svg$"))
        self.assertEqual(self.page_errors, [])

    def test_account_profile_edit_settings_and_logout_back_state(self):
        self.page.goto(self.base_url + "/app.html?browser=account#account", wait_until="domcontentloaded")
        account_panel = self.page.locator("#account")
        expect(account_panel).to_be_visible()

        home_box = self.page.locator(".homebtn--float").bounding_box()
        header_box = account_panel.locator(".cc-account-header").bounding_box()
        self.assertIsNotNone(home_box)
        self.assertIsNotNone(header_box)
        self.assertGreaterEqual(header_box["y"], home_box["y"] + home_box["height"])

        self.page.locator("#tSet").click()
        expect(self.page.locator("#settings")).to_be_visible()
        expect(self.page.locator("#settings")).to_contain_text("Sparko tips")
        expect(self.page.locator("#tSet")).to_have_attribute("aria-current", "true")
        expect(self.page.locator("#tAccount")).to_have_attribute("aria-current", "false")
        self.assertEqual(self.page.locator("#settings input[name='nickname']").count(), 0)
        self.page.get_by_role("button", name="Back to Account").click()

        account_panel.get_by_role("button", name="Create account").click()
        form = self.page.locator(".cc-auth-form")
        form.locator('[name="nickname"]').fill("Review Tester")
        form.locator('[name="email"]').fill(f"review-{uuid.uuid4().hex[:12]}@example.com")
        form.locator('[name="password"]').fill("a secure test phrase 2026!")
        form.get_by_role("button", name="Create account").click()
        expect(account_panel.get_by_role("heading", name="Your account")).to_be_visible()
        nickname = account_panel.locator("input[name='nickname']")
        expect(nickname).to_have_value("Review Tester")

        nickname.fill("Saved Nickname")
        account_panel.get_by_role("button", name="Use Flower profile icon").click()
        save = account_panel.get_by_role("button", name="Save changes")
        expect(save).to_be_enabled()
        save.click()
        expect(account_panel.locator("#ccAccountStatus")).to_have_text("Saved")
        expect(account_panel.get_by_role("heading", name="Saved Nickname")).to_be_visible()
        expect(nickname).to_have_value("Saved Nickname")
        expect(account_panel.locator(".cc-profile-avatar img")).to_have_attribute("src", re.compile(r"profile-flower\.svg$"))
        nickname.fill("Discard this draft")
        account_panel.get_by_role("button", name="Cancel").click()
        expect(account_panel.locator("input[name='nickname']")).to_have_value("Saved Nickname")

        self.page.locator("#tSet").click()
        self.page.get_by_role("button", name="Back to Account").click()
        self.page.reload(wait_until="domcontentloaded")
        expect(account_panel.get_by_role("heading", name="Saved Nickname")).to_be_visible()
        expect(account_panel.locator(".cc-profile-icon-option[aria-pressed='true']")).to_have_attribute("aria-label", "Use Flower profile icon")

        account_panel.get_by_role("button", name="Log out & continue as guest").click()
        expect(self.page).to_have_url(re.compile(r"#map$"))
        expect(self.page.locator("#tAccount")).to_have_attribute("aria-label", "Create or access your account")
        expect(self.page.locator("#account .cc-profile-avatar img")).to_have_attribute("src", re.compile(r"profile-guest\.svg$"))

        self.page.go_back(wait_until="domcontentloaded")
        expect(self.page.locator("#settings")).to_be_visible()
        expect(self.page.locator("#settings")).not_to_contain_text("Saved Nickname")
        self.page.go_back(wait_until="domcontentloaded")
        expect(account_panel).to_be_visible()
        expect(account_panel).to_contain_text("Sign in to keep your favorites close")
        expect(account_panel).not_to_contain_text("Saved Nickname")
        self.assertEqual(self.page_errors, [])

    def test_profile_frame_uses_server_verification_flag(self):
        fixture = {
            "user": {
                "id": "ucla-fixture",
                "nickname": "Verified Fixture",
                "email": "fixture@ucla.edu",
                "ucla_email_claimed": True,
                "is_verified_ucla": False,
                "email_verified_at": None,
            },
            "saved_event_ids": [],
        }

        def auth_fixture(route):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(fixture))

        self.page.route("**/api/auth/me", auth_fixture)
        self.page.goto(self.base_url + "/app.html?fixture=verification#account", wait_until="domcontentloaded")
        expect(self.page.locator("#account .cc-profile-avatar")).to_be_visible()
        self.assertEqual(self.page.locator("#account .cc-profile-avatar.is-ucla-verified").count(), 0)
        self.assertEqual(self.page.locator("#account .cc-profile-avatar.is-ucla-verified").count(), 0)

        fixture["user"]["is_verified_ucla"] = True
        fixture["user"]["email_verified_at"] = "2026-11-08T12:00:00+00:00"
        self.page.reload(wait_until="domcontentloaded")
        expect(self.page.locator("#account .cc-profile-avatar.is-ucla-verified")).to_be_visible()
        expect(self.page.locator("#account .cc-profile-star")).to_be_visible()
        self.assertEqual(self.page_errors, [])

    def test_registration_form_fits_a_mobile_viewport(self):
        self.advance_intro_to_invitation()
        self.page.get_by_role("button", name="Create account").click()
        modal = self.page.locator(".cc-modal").bounding_box()
        app_box = self.page.locator("#app").bounding_box()
        self.assertIsNotNone(modal)
        self.assertIsNotNone(app_box)
        self.assertGreaterEqual(modal["x"], app_box["x"])
        self.assertGreaterEqual(modal["y"], app_box["y"])
        self.assertLessEqual(modal["x"] + modal["width"], app_box["x"] + app_box["width"] + 1)
        self.assertLessEqual(modal["y"] + modal["height"], app_box["y"] + app_box["height"] + 1)
        expect(self.page.locator(".cc-auth-form input[name='password']")).to_be_visible()
        self.assertEqual(self.page_errors, [])

    def test_account_saves_and_onboarding_resume_after_reload(self):
        self.page.set_viewport_size({"width": 1280, "height": 900})
        self.advance_intro_to_invitation()
        self.page.get_by_role("button", name="Create account").click()
        form = self.page.locator(".cc-auth-form")
        form.locator('[name="nickname"]').fill("Tour Tester")
        form.locator('[name="email"]').fill(f"tour-{uuid.uuid4().hex[:12]}@example.com")
        form.locator('[name="password"]').fill("a secure test phrase 2026!")
        form.get_by_role("button", name="Create account").click()
        expect(self.page.locator("#ccTourLayer")).to_be_visible()

        self.page.locator('[data-tour="category-arts"]').click()
        self.page.locator(".cc-tour-next").click()
        self.open_highlighted_event()
        expect(self.page.locator("#sheetTitle")).to_be_visible()
        self.page.locator(".cc-tour-next").click()
        self.page.locator('[data-tour="event-save"]').click()
        expect(self.page.locator('[data-tour="event-save"]')).to_have_attribute("aria-pressed", "true")

        self.page.reload(wait_until="domcontentloaded")
        expect(self.page.locator("#ccTourLayer")).to_be_visible()
        expect(self.page.locator(".cc-tour-count")).to_have_text("3 / 4")
        expect(self.page.locator('[data-tour="event-save"]')).to_have_attribute("aria-pressed", "true")
        self.assertTrue(self.page.evaluate("window.CampusCornersAccount.isAuthenticated()"))
        self.assertEqual(self.page_errors, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
