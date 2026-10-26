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

Visitors' saved events, follows, reviews and added spots are kept in their own browser for now.

## To do before going public

- Put the team's contact email in `about.html` (search for `TODO`).
- Confirm that the UCLA campus map may be used publicly.
- Events only cover the dates in the app repo's `data/events/`. Refresh them there, then run the script above.

## Preview on your computer

```
python3 -m http.server 8000
```

Then open http://localhost:8000.
