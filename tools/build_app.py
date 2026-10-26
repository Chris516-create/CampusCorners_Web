"""Bring the Campus Corners app into the website.

The app itself lives in the app repo (Chris516-create/Campus-Corners, folder prototype/).
This script copies it into this website as the full-screen page app.html, so the app is
only ever edited in one place. Run it again whenever the app or its events change:

    python3 tools/build_app.py ../Campus-Corners

It writes: app.html, app/app.css, app/app.js and the images the app needs under app/.
Do not edit those by hand; change the app repo (or css/app-shell.css for the website look).

If the app's code has changed in a way this script does not expect, it stops with a clear
message instead of producing a half-working page.
"""
import json
import sys as _sys
_sys.exit("Since Oct 25, 2026 the app is edited directly in this repo (app.html, app/). This script would overwrite it with the old prototype, so it is retired. See README.")
import shutil
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]
APP = Path(sys.argv[1] if len(sys.argv) > 1 else WEB.parent / "Campus-Corners").resolve()
SRC = APP / "prototype/src/index.template.html"
if not SRC.exists():
    sys.exit(f"Can't find the app at {APP}. Pass the path to the Campus-Corners repo.")
OUT = WEB / "app"
OUT.mkdir(exist_ok=True)

html = SRC.read_text(encoding="utf-8")


def between(text, start, end):
    a = text.index(start) + len(start)
    return text[a:text.index(end, a)]


def swap(text, old, new, count=1):
    """Replace `old` with `new`, and stop if the app no longer contains it `count` times."""
    found = text.count(old)
    if found != count:
        sys.exit(f"The app changed: expected {count}x {old[:70]!r}, found {found}. Update tools/build_app.py.")
    return text.replace(old, new)


css = between(html, "<style>", "</style>")
js = between(html, "<script>", "</script>")
markup = html[html.index('<div class="app" id="app">'):html.index("<script>")].rstrip()
for _ in range(3):  # closes of .phone, .phone-col and .wrap, which the website doesn't use
    if not markup.endswith("</div>"):
        sys.exit("The app's page structure changed. Update tools/build_app.py.")
    markup = markup[:-len("</div>")].rstrip()

# ---- events: same rule as the app's own build (all files merged, cancelled events dropped)
events = {}
for f in sorted((APP / "data/events").glob("*.json")):
    for e in json.loads(f.read_text(encoding="utf-8")):
        if e.get("status") != "cancelled":
            events[e["id"]] = e
js = swap(js, "__EVENTS__", json.dumps(list(events.values()), ensure_ascii=False))

# ---- images are files on the website instead of being pasted into the page
SPARKO_INLINE = "data:image/webp;base64,__SPARKO__"
markup = swap(markup, SPARKO_INLINE, "app/sparko.webp")
js = swap(js, SPARKO_INLINE, "app/sparko.webp")
js = swap(js, 'const POSTERS="../assets/posters/"', 'const POSTERS="app/posters/"')
js = swap(js, 'const STK="../assets/stickers/"', 'const STK="app/stickers/"')
for name in ("ucla-map-events.jpg", "ucla-map-explore.jpg", "ucla-map-planetarium.jpg"):
    js = swap(js, f'"{name}"', f'"app/{name}"')
    shutil.copy2(APP / "prototype" / name, OUT / name)
shutil.copy2(APP / "assets/sparko/sparko.webp", OUT / "sparko.webp")
for folder, pattern in (("stickers", "*.webp"), ("posters", "*.jpg")):
    (OUT / folder).mkdir(exist_ok=True)
    for old in (OUT / folder).iterdir():
        old.unlink()
    for f in sorted((APP / "assets" / folder).glob(pattern)):
        shutil.copy2(f, OUT / folder / f.name)

# ---- "today" is the real date. The app prototype always opens on its first day.
js = swap(js, "const BASE=new Date(2026,9,5),NDAYS=14;",
          "const BASE=new Date(2026,9,5),NDAYS=14;"
          "const _t=Math.round((new Date(new Date().toDateString())-BASE)/864e5),"
          "TODAY=_t>=0&&_t<NDAYS?_t:-1,FROM=Math.max(TODAY,0);")
js = swap(js, 'const S={mode:"events",day:0,', 'const S={mode:"events",day:FROM,')
js = swap(js, '$("today").disabled=S.day===0;', '$("today").disabled=TODAY<0||S.day===TODAY;')
js = swap(js, '${i===0?"Today":fmt(d,{weekday:"short"})}', '${i===TODAY?"Today":fmt(d,{weekday:"short"})}')
js = swap(js, '${S.day===0?"today":"this day"}', '${S.day===TODAY?"today":"this day"}')
js = swap(js, '$("today").onclick=()=>{S.day=0;', '$("today").onclick=()=>{S.day=FROM;')
# the opening poster and the recommendations only show events that haven't passed
js = swap(js, "const pool=EVENTS.filter(e=>e.poster);",
          "const pool=EVENTS.filter(e=>e.poster&&e.days.some(d=>d>=FROM));")
js = swap(js, "const ev=RECS.map(id=>EVENTS.find(e=>e.id===id)).filter(Boolean)",
          "const ev=RECS.map(id=>EVENTS.find(e=>e.id===id)).filter(e=>e&&e.days.some(d=>d>=FROM))")
js = swap(js, '$("recBtn").setAttribute("aria-expanded",S.recOpen);',
          '$("recBtn").setAttribute("aria-expanded",S.recOpen);'
          '$("recBtn").hidden=!RECS.some(id=>{const e=EVENTS.find(x=>x.id===id);return e&&e.days.some(d=>d>=FROM)});')

# ---- remember saved events, stickers and settings in this browser
js = swap(js, "selStk:null,lastFound:null};",
          "selStk:null,lastFound:null};\n"
          'try{const m=JSON.parse(localStorage.getItem("campus-corners")||"null");if(m){'
          "S.saved=new Set(m.saved||[]);S.went=new Set(m.went||[]);S.stickers=new Set(m.stickers||[]);"
          'if(m.tips===false)S.tips=false;if(typeof m.skin==="string")S.skin=m.skin}}catch(_){}\n'
          'function persist(){try{localStorage.setItem("campus-corners",JSON.stringify({saved:[...S.saved],went:[...S.went],'
          "stickers:[...S.stickers],tips:S.tips,skin:S.skin}))}catch(_){}}")
js = swap(js, "function render(){\n", "function render(){\n  persist();\n")
js = swap(js, "render();applySkinImgs();\nrequestAnimationFrame(fitDay);",
          'if(S.skin!=="default"&&S.stickers.has(S.skin))applySkin(S.skin);else{S.skin="default";render();applySkinImgs()}\n'
          "requestAnimationFrame(fitDay);")

# ---- wording that only made sense inside the phone prototype
js = swap(js, "Follows your iPhone's Reduce Motion setting.", "Follows your device's Reduce Motion setting.")
js = swap(js, "The camera isn't available in this preview.", "Scanning comes with the iPhone app. Here you can try it out.")
js = swap(js, "Every event links to its source.</small>",
          'Every event links to its source. Showing ${fmt(dayDate(0),{month:"short",day:"numeric"})} – '
          '${fmt(dayDate(NDAYS-1),{month:"short",day:"numeric"})}.</small>')

# ---- the website's way back home (round logo button), in the top row and floating
HOME = ('<a class="homebtn {cls}" href="./" aria-label="Campus Corners home">'
        '<img src="img/logo.svg" alt=""></a>')
markup = swap(markup, '<div class="toprow">', '<div class="toprow">\n            ' + HOME.format(cls="homebtn--row"))
markup = swap(markup, '<div class="app" id="app">', '<div class="app" id="app">\n        ' + HOME.format(cls="homebtn--float"))

(OUT / "app.css").write_text("/* Copied from the app repo by tools/build_app.py. Don't edit here. */\n" + css.strip() + "\n", encoding="utf-8")
(OUT / "app.js").write_text("/* Copied from the app repo by tools/build_app.py. Don't edit here. */\n" + js.strip() + "\n", encoding="utf-8")

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Explore · Campus Corners</title>
<meta name="description" content="Every UCLA campus event on one map, day by day.">
<link rel="icon" href="img/logo.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="img/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Outfit:wght@500;600&display=swap">
<link rel="stylesheet" href="app/app.css">
<link rel="stylesheet" href="css/app-shell.css">
</head>
<body class="app-page">
<!-- Built by tools/build_app.py from the app repo. Don't edit this file by hand. -->
<main>
      __APP__
</main>
<noscript><p style="padding:24px;font:16px system-ui">The campus map needs JavaScript. <a href="./">Back to Campus Corners</a></p></noscript>
<script src="app/app.js"></script>
</body>
</html>
"""
(WEB / "app.html").write_text(PAGE.replace("__APP__", markup), encoding="utf-8")
days = sorted(d for e in events.values() for d in e["dates"])
print(f"app.html built from {APP.name}: {len(events)} events, {days[0]} to {days[-1]}")
