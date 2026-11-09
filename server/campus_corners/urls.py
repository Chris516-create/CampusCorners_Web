from django.contrib.staticfiles.views import serve as staticfiles_serve
from django.http import FileResponse, Http404
from django.urls import include, path, re_path

from accounts.admin import site as campus_corners_admin
from accounts import api


urlpatterns = [
    path("admin/", campus_corners_admin.urls),
    path("api/", include("accounts.urls")),
    re_path(r"^api/.*$", api.api_not_found),
    path("", api.public_page, {"filename": "index.html"}),
    path("app.html", api.public_page, {"filename": "app.html"}),
    path("about.html", api.public_page, {"filename": "about.html"}),
    path("stickers.html", api.public_page, {"filename": "stickers.html"}),
    path("404.html", api.public_page, {"filename": "404.html"}),
    path("favicon.ico", api.public_page, {"filename": "favicon.ico"}),
    path("site.webmanifest", api.public_page, {"filename": "site.webmanifest"}),
    re_path(r"^(?P<path>(?:app|css|img|js)/.+)$", staticfiles_serve, {"insecure": True}),
]

handler404 = "accounts.api.not_found"
handler500 = "accounts.api.server_error"
