# Campus Corners website

The website for [campus-corners.com](https://campus-corners.com). Plain HTML, CSS and JavaScript: there is nothing to install and no build step for the pages.

| Page | File | What it is |
| --- | --- | --- |
| Home | `index.html` | Logo, Sparko and the button into the map |
| Explore | `app.html` | The Campus Corners app, full screen |
| About | `about.html` | Campus Corners and Sparko |
| Stickers | `stickers.html` | Product photos (display only, nothing is sold here) |

The look (sunset sky, glass panels, Outfit and DM Sans) comes from the Figma Make file "Four-Page Campus Website". Shared styles are in `css/site.css`.

## Where the app is edited

Since Oct 25, 2026 the app (`app.html`, `app/app.js`, `app/app.css`) is edited **in this repo**. It has moved well past the old prototype in the Campus-Corners repo (Shuffle, clubs, reviews, orange Explore, Sparko's route guide), so `tools/build_app.py` no longer applies and stops with a note if you run it.

The Campus-Corners repo still holds the data and the tools that feed the site:

- events: `data/events/` (built each week from the UCLA calendar and `data/scripts/fetch_instagram_week.py`)
- clubs: `data/clubs/ucla-clubs.json`, restrooms and study spots: `data/explore/spots.json`
- maps: `tools/recolor_line.py` (pink and orange line maps), `tools/footprints.py` (building outlines), `tools/walkgrid.py` (walkable grid for the route guide)

Guest saves, follows, reviews and added spots stay in that browser. Signed-in saved events and Sparko tour progress sync to the account through the local Django API.

## Account scope

Accounts support email/password sign-in and profile edits. Signup passwords can be 8–128 characters and are stored as Argon2 hashes. Each SQL profile stores a nickname and a `profile_icon` key; new accounts default to `sparko`, the site mascot. The picker also offers a star, flower, and heart. The database stores these short keys, not image data; the website maps each key to a bundled image. The UCLA profile frame is shown only when the server marks an account's UCLA email as verified. Email verification delivery, UCLA single sign-on, email or password changes, and uploaded pictures are outside this review. Registration does not send email.

The homepage **Explore the map** action opens the map directly. Guests see the login form in a floating dialog over the map and can continue as a guest; signed-in visitors go straight to the map. The four-item bottom bar keeps Settings, and a separate floating Account button opens the dedicated account screen. Guests use a warm-toned profile silhouette.

### What is stored

- `accounts_user`: UUID primary key, normalized unique email, nickname, `profile_icon` key, Argon2 password hash, account dates, and optional email verification date.
- `accounts_userpreferences`: email choice and its timestamps.
- `accounts_useronboarding`: tour status, current step, and a JSON list of skipped steps.
- `accounts_savedevent`: one row per saved event, with the event key and saved date.
- `django_session`: server-side session content; the browser cookie contains only the opaque session identifier.

The signed-in user's profile is also returned by `/api/auth/me` as JSON. Profile updates go through `/api/me/profile`, which only accepts `nickname` and an allowed `profile_icon` key. The staff page at `/admin/` reads the same database; it masks email in account lists and excludes password hashes and session contents.

## Staff data center

The Django backend provides a preliminary read-only HTML data center at `/admin/`. It is protected by Django staff sign-in. The account list masks email addresses; an authorized account detail page shows the full email. Staff can inspect account profile fields, saved-event rows, preferences, and current tour progress. Password hashes, active sessions, temporary rate-limit rows, editing, and deletion are excluded.

After applying migrations, create an administrator interactively on the machine that runs Django:

~~~
server/var/venv/bin/python server/manage.py createsuperuser
~~~

The command prompts for the administrator email, nickname, and password. Keep that credential outside this repository. Then open `http://localhost:8000/admin/` while the local server is running. The local records are stored in SQLite at `server/var/dev.sqlite3` by default; `DJANGO_SQLITE_NAME` can choose another file and `DATABASE_URL` selects PostgreSQL. A hosted admin needs the Django backend and a shared persistent database; the static site alone cannot securely serve private account records. No administrator credential is created by the app.

## To do before going public

- Put the team's contact email in `about.html` (search for `TODO`).
- Confirm that the UCLA campus map may be used publicly.
- Events only cover the dates in the app repo's `data/events/`. Refresh them there, then run the script above.

## Preview on your computer

The local review server serves the existing site and /api/ from the same origin.
Use Python 3.12 and the Django dependencies in server/requirements.txt.

~~~
python3.12 -m venv server/var/venv
server/var/venv/bin/python -m pip install -r server/requirements.txt
cp server/.env.example server/.env
~~~

Replace the example secret in server/.env with a random value, then run:

~~~
server/var/venv/bin/python server/manage.py migrate
server/var/venv/bin/python server/manage.py runserver
~~~

Open http://localhost:8000/app.html. SQLite data lives in the ignored
server/var/dev.sqlite3 file. For a hosted WSGI preview, set DATABASE_URL to
PostgreSQL, set a stable DJANGO_SECRET_KEY, use secure cookies and HTTPS, then
run collectstatic; the static source allowlist contains only app/, css/, img/,
and js/.

For the Django and browser checks, install `server/requirements-dev.txt` and run
`server/var/venv/bin/python -m playwright install chromium`. Then run
`server/var/venv/bin/python server/manage.py test accounts` and
`server/var/venv/bin/python server/accounts/browser_tests.py`. The browser check
uses a temporary database and preview server.

The historical events in the map remain a sample week and are not current listings.
