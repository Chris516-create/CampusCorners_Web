#!/usr/bin/env python3
"""Add a week's events to the site and rebuild the app's event data.

Each person adds their own file, so two people never overwrite each other:
    events/<week>/calendar.json   UCLA Community calendar events (Part A person)
    events/<week>/clubs-A.json    club events from clubs #1-150   (Part A person)
    events/<week>/clubs-B.json    club events from clubs #151-300 (Part B person)

Run from the CampusCorners_Web folder:

    python3 tools/update_site.py --week 2026-11-09 --add ~/Campus-Corners/data/events/2026-11-09/clubs-A.json \\
        --posters ~/Campus-Corners/assets/posters/incoming/2026-11-09 \\
        --clubs ~/Campus-Corners/data/clubs/ucla-clubs.json --avatars ~/Campus-Corners/data/clubs/avatars

    python3 tools/update_site.py --week 2026-11-09 --check     # validate and show the summary only

What it does:
  1. checks every event (fields, category, dates, place ids, source link) and stops on errors
  2. copies the file to events/<week>/<same name>.json
  3. resizes the posters those events use into app/posters/
  4. refreshes the club list and profile pictures used by club search (with --clubs/--avatars)
  5. rebuilds the events inside app/app.js from every file in events/<week>/ and sets the app to
     show exactly that week, Monday to Sunday (the site always shows the coming week only)
Needs Python 3. Uses Pillow to resize images if installed, otherwise macOS `sips`.
"""
import argparse, datetime as dt, hashlib, json, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "app.js"
EVENTS_DIR = ROOT / "events"
POSTERS = ROOT / "app" / "posters"
AVATARS = ROOT / "app" / "clubs"
CATS = {"academic", "arts", "community", "wellness", "sports", "career"}
LOCS = {"confirmed", "tbd", "online", "offcampus", "multiple"}
NEEDED = ["id", "title", "dates", "startTime", "endTime", "timeStatus", "placeId", "placeText", "locationStatus",
          "category", "host", "description", "sourceUrls", "status", "conflicts", "needsReview"]
FIELD_COLORS = {  # club search colours, one per field in the club directory
    "Academic & Research": "#6D5BD0", "Arts & Performance": "#D63C93", "Biology, Chemistry & Research": "#2E9E6A",
    "Business & Careers": "#2F7BEA", "Culture & Identity": "#1E9A5C", "Engineering & Technology": "#5B4BC4",
    "Environment & Sustainability": "#3F8F3A", "Faith & Spirituality": "#8C6D3F", "Government & Leadership": "#3F5BA9",
    "Greek Life": "#B5487A", "Law, Policy & Debate": "#34508F", "Media & Publications": "#C2410C",
    "Medicine & Pre-Health": "#0E9C9C", "Psychology, Neuroscience & Wellness": "#8E5BD0", "Service & Advocacy": "#E8661F",
    "Social & Hobbies": "#D9822B", "Sports & Recreation": "#D99600"}


def places(js):
    blk = js[js.index("const PLACES={"):js.index("};", js.index("const PLACES={"))]
    return set(re.findall(r"(\w+):\{n:\"", blk))


def resize(src, dest, box, square=False):
    try:
        from PIL import Image
        im = Image.open(src).convert("RGB")
        if square:
            w, h = im.size; s = min(w, h)
            im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((box, box))
        else:
            im.thumbnail((box, box))
        im.save(dest, quality=82, optimize=True, progressive=True)
        return
    except ImportError:
        pass
    if shutil.which("sips"):
        shutil.copyfile(src, dest)
        subprocess.run(["sips", "-Z", str(box), str(dest)], capture_output=True)
    else:
        shutil.copyfile(src, dest)


def check(events, week, known_places, name):
    errs, warns, ids = [], [], set()
    lo, hi = week - dt.timedelta(days=7), week + dt.timedelta(days=7)
    for i, e in enumerate(events):
        tag = "%s #%d %s" % (name, i + 1, e.get("id", "?"))
        miss = [k for k in NEEDED if k not in e]
        if miss:
            errs.append("%s: missing %s" % (tag, ", ".join(miss))); continue
        if e["id"] in ids:
            errs.append("%s: duplicate id" % tag)
        ids.add(e["id"])
        if e["category"] not in CATS:
            errs.append("%s: category must be one of %s" % (tag, ", ".join(sorted(CATS))))
        if e["locationStatus"] not in LOCS:
            errs.append("%s: locationStatus must be one of %s" % (tag, ", ".join(sorted(LOCS))))
        if not e["dates"]:
            errs.append("%s: no dates" % tag)
        for d in e["dates"]:
            try:
                day = dt.date.fromisoformat(d)
            except ValueError:
                errs.append("%s: bad date %r" % (tag, d)); continue
            if not lo <= day < hi:
                warns.append("%s: date %s is outside this week" % (tag, d))
        for t in (e["startTime"], e["endTime"]):
            if t is not None and not re.fullmatch(r"\d\d:\d\d", t):
                errs.append("%s: time %r must be HH:MM (24-hour) or null" % (tag, t))
        if e["placeId"] is not None and e["placeId"] not in known_places:
            errs.append("%s: placeId %r is not on the map; add it to PLACES in app/app.js first, or use null" % (tag, e["placeId"]))
        if e["placeId"] and e["locationStatus"] in ("tbd", "online", "offcampus"):
            errs.append("%s: has placeId but locationStatus is %s" % (tag, e["locationStatus"]))
        if e["locationStatus"] == "confirmed" and not e["placeId"]:
            warns.append("%s: confirmed place but no placeId, so it will not be on the map" % tag)
        if not e["sourceUrls"]:
            errs.append("%s: needs a source link" % tag)
    return errs, warns


def stamp_versions():
    """Give app.js and app.css a ?v=<content hash> in app.html so browsers fetch the new files at once."""
    page = ROOT / "app.html"
    html = page.read_text(encoding="utf-8")
    for name in ("app/app.js", "app/app.css"):
        v = hashlib.md5((ROOT / name).read_bytes()).hexdigest()[:8]
        html = re.sub(r'(["\'])' + re.escape(name) + r'(\?v=[0-9a-f]+)?(["\'])', r"\g<1>%s?v=%s\g<3>" % (name, v), html)
    page.write_text(html, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Add a week's events to the site and rebuild the app's event data.")
    ap.add_argument("--week", required=True, help="Monday of the week, YYYY-MM-DD")
    ap.add_argument("--add", action="append", default=[], help="an events JSON file to add (calendar.json, clubs-A.json, clubs-B.json)")
    ap.add_argument("--posters", help="folder with the fetched post images (<media id>.jpg)")
    ap.add_argument("--clubs", help="data/clubs/ucla-clubs.json from the Campus-Corners repo")
    ap.add_argument("--avatars", help="data/clubs/avatars from the Campus-Corners repo")
    ap.add_argument("--check", action="store_true", help="validate and summarise only; change nothing")
    args = ap.parse_args()
    week = dt.date.fromisoformat(args.week)
    if week.weekday() != 0:
        sys.exit("--week must be a Monday")
    js = APP.read_text(encoding="utf-8")
    known = places(js)
    wdir = EVENTS_DIR / week.isoformat()

    # 1-3: validate and add the new files
    bad = False
    for f in args.add:
        p = Path(f).expanduser()
        evs = json.loads(p.read_text(encoding="utf-8"))
        errs, warns = check(evs, week, known, p.name)
        for w in warns:
            print("  note:", w)
        for e in errs:
            print("  ERROR:", e)
        bad |= bool(errs)
        if errs or args.check:
            continue
        wdir.mkdir(parents=True, exist_ok=True)
        (wdir / p.name).write_text(json.dumps(evs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for e in evs:
            if e.get("poster"):
                dest = POSTERS / e["poster"]
                src = Path(args.posters).expanduser() / e["poster"] if args.posters else None
                if not dest.exists():
                    if src and src.exists():
                        resize(src, dest, 1350)
                    else:
                        print("  ERROR: poster %s not found (pass --posters)" % e["poster"]); bad = True
        print("added %s: %d events" % (p.name, len(evs)))
    if bad:
        sys.exit("\nFix the errors above and run again. Nothing was rebuilt.")

    # 4: club list and profile pictures
    clubs_js = None
    if args.clubs:
        clubs = json.loads(Path(args.clubs).expanduser().read_text(encoding="utf-8"))
        av = Path(args.avatars).expanduser() if args.avatars else None
        if av and not args.check:
            AVATARS.mkdir(exist_ok=True)
            for c in clubs:
                src, dest = av / (c["instagram"] + ".jpg"), AVATARS / (c["instagram"] + ".jpg")
                if src.exists() and not dest.exists():
                    resize(src, dest, 96, square=True)
        have = {p.name for p in AVATARS.glob("*.jpg")}
        clubs_js = [{"n": c["name"], "h": c["instagram"], "g": c.get("field") or c.get("group") or "",
                     "a": c["instagram"] + ".jpg" if c["instagram"] + ".jpg" in have else None} for c in clubs]

    # 5: rebuild the app's events
    base = week  # the app always shows the coming week, Monday to Sunday
    end = week + dt.timedelta(days=7)
    raw, seen = [], set()
    for folder in sorted(EVENTS_DIR.glob("*/")):
        try:
            fw = dt.date.fromisoformat(folder.name)
        except ValueError:
            continue
        if fw + dt.timedelta(days=7) <= base or fw >= end:
            continue
        for f in sorted(folder.glob("*.json")):
            for e in json.loads(f.read_text(encoding="utf-8")):
                if e["id"] in seen:
                    continue
                if any(base <= dt.date.fromisoformat(d) < end for d in e["dates"]):
                    seen.add(e["id"]); raw.append(e)
    raw.sort(key=lambda e: (min(e["dates"]), e.get("startTime") or "99"))
    ndays = (end - base).days
    by_day = {}
    for e in raw:
        for d in e["dates"]:
            if base <= dt.date.fromisoformat(d) < end:
                by_day.setdefault(d, [0, 0]); by_day[d][0] += 1; by_day[d][1] += bool(e["placeId"])
    print("\nThe app will show %s – %s (%d days), %d events:" % (base.strftime("%a %b %-d"), (end - dt.timedelta(days=1)).strftime("%a %b %-d"), ndays, len(raw)))
    for d in sorted(by_day):
        print("  %s  %3d events, %3d on the map" % (dt.date.fromisoformat(d).strftime("%a %b %-d"), *by_day[d]))
    files = sorted(p.name for p in wdir.glob("*.json")) if wdir.exists() else []
    print("Files for this week: %s" % (", ".join(files) or "none yet"))
    if args.check:
        return

    js = re.sub(r"const BASE=new Date\([^)]*\),NDAYS=\d+;",
                "const BASE=new Date(%d,%d,%d),NDAYS=%d;" % (base.year, base.month - 1, base.day, ndays), js, count=1)
    i = js.index("const RAW="); j = js.index("\n", i)
    js = js[:i] + "const RAW=" + json.dumps(raw, ensure_ascii=False) + ";" + js[j:]
    # Recommended: keep picks that are still on, then fill with club events that have posters, one per day
    m = re.search(r"const RECS=(\[[^\]]*\]);", js)
    ids = {e["id"] for e in raw}
    recs = [r for r in json.loads(m.group(1)) if r in ids]
    for e in raw:
        if len(recs) >= 6:
            break
        if e.get("poster") and e["placeId"] and e["id"] not in recs and min(e["dates"]) not in {min(x["dates"]) for x in raw if x["id"] in recs}:
            recs.append(e["id"])
    js = js[:m.start()] + "const RECS=" + json.dumps(recs) + ";" + js[m.end():]
    if clubs_js is not None:
        js = re.sub(r"const CLUBS=\[.*?\];", lambda _: "const CLUBS=" + json.dumps(clubs_js, ensure_ascii=False, separators=(",", ":")) + ";", js, count=1, flags=re.S)
        gm = re.search(r"const GROUPC=\{[^}]*\};", js)
        if gm:
            js = js[:gm.start()] + "const GROUPC=" + json.dumps(FIELD_COLORS, ensure_ascii=False) + ";" + js[gm.end():]
    APP.write_text(js, encoding="utf-8")
    stamp_versions()
    print("\nUpdated app/app.js. Next: preview, then commit and open a pull request (see the weekly-events skill).")


if __name__ == "__main__":
    main()
