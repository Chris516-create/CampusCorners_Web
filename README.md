# Campus Corners website

The website for [campus-corners.com](https://campus-corners.com). Plain HTML, CSS and JavaScript: there is nothing to install and no build step for the pages.

| Page | File | What it is |
| --- | --- | --- |
| Home | `index.html` | Logo, Sparko and the button into the map |
| Explore | `app.html` | The Campus Corners app, full screen |
| About | `about.html` | Campus Corners and Sparko |
| Stickers | `stickers.html` | Product photos (display only, nothing is sold here) |

The look (sunset sky, glass panels, Outfit and DM Sans) comes from the Figma Make file "Four-Page Campus Website". Shared styles are in `css/site.css`.

## The app comes from the app repo

The app is developed in [Campus-Corners](https://github.com/Chris516-create/Campus-Corners) (`prototype/`). This repo holds a copy, made by a script, so the app is only edited in one place.

**Do not edit `app.html` or anything in `app/` by hand.** After the app or its events change, update the copy:

```
python3 tools/build_app.py ../Campus-Corners
```

Then commit the changed files. The script stops with a message if the app's code changed in a way it does not expect.

What the script changes for the website (everything else is the app as is):

- "Today" is the real date, and the app opens on it. The opening poster and the recommendations only show events that have not passed.
- Saved events, collected stickers and settings are remembered in the visitor's browser.
- A round logo button leads back to the home page.
- `css/app-shell.css` controls how the app sits in the page: full screen on phones, floating glass panels over the map on wide screens.

Event rules (source link required, never guess a location, no Instagram scraping) are in the app repo's README and apply here unchanged, because the events are copied from there.

## To do before going public

- Put the team's contact email in `about.html` (search for `TODO`).
- Confirm that the UCLA campus map may be used publicly.
- Events only cover the dates in the app repo's `data/events/`. Refresh them there, then run the script above.

## Preview on your computer

```
python3 -m http.server 8000
```

Then open http://localhost:8000.
