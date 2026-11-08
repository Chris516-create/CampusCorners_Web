#!/usr/bin/env python3
"""Find a building's position for PLACES in app/app.js.

Draws a labelled grid (in map units, the numbers PLACES uses) over part of the campus map so you
can read off a building's x and y. Map units run x 0-1224, y 0-1584; central campus is about
x 600-1100, y 350-950.

    python3 tools/map_grid.py 830 560 980 680 grid.png     # x0 y0 x1 y1 out.png

Open grid.png, find the building's label, and add it to PLACES, e.g.
    pab:{n:"Physics and Astronomy Building",x:893,y:612},
Needs Pillow (pip3 install pillow).
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

x0, y0, x1, y1 = map(int, sys.argv[1:5])
out = sys.argv[5] if len(sys.argv) > 5 else "grid.png"
im = Image.open(Path(__file__).resolve().parents[1] / "app" / "ucla-map-lines.jpg").convert("RGB")
c = im.crop((x0 * 3, y0 * 3, x1 * 3, y1 * 3))
d = ImageDraw.Draw(c)
step = 25 if max(x1 - x0, y1 - y0) <= 300 else 50
for gx in range((x0 // step + 1) * step, x1, step):
    d.line([((gx - x0) * 3, 0), ((gx - x0) * 3, c.height)], fill=(0, 140, 255), width=2)
    d.text(((gx - x0) * 3 + 4, 4), str(gx), fill=(0, 90, 220))
for gy in range((y0 // step + 1) * step, y1, step):
    d.line([(0, (gy - y0) * 3), (c.width, (gy - y0) * 3)], fill=(0, 140, 255), width=2)
    d.text((4, (gy - y0) * 3 - 14), str(gy), fill=(0, 90, 220))
c.save(out)
print("saved", out)
