# Local Django review server

The server runs the website and its JSON API on one origin. It uses SQLite in
server/var/dev.sqlite3 by default. DATABASE_URL, when present, must be a valid
PostgreSQL URL; the server does not silently fall back to SQLite.

Create server/.env from .env.example, replace the placeholder with a stable
random DJANGO_SECRET_KEY, install requirements.txt, run migrations, then start
manage.py runserver. The only local HTTP cookie exception is for localhost;
review deployments require HTTPS and secure cookies.

Static files are limited to the public HTML pages and the app/, css/, img/, and
js/ directories. The Django development server handles these paths locally.
For a later WSGI preview, collect those allowlisted files and serve them through
WhiteNoise. Deployment is not part of this feature.
