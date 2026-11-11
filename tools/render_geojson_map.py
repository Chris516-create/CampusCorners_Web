#!/usr/bin/env python3
"""Render the supplied UCLA GeoJSON building and road layers as an SVG base map."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDINGS = ROOT / "app" / "map-data" / "ucla_buildings.geojson"
ROADS = ROOT / "app" / "map-data" / "ucla_highway.geojson"
OUTPUT = ROOT / "app" / "ucla-campus-map.svg"
BUILDING_INDEX = ROOT / "app" / "ucla-campus-buildings.js"
WIDTH, HEIGHT = 1224, 1584

# Affine fit from 25 named GeoJSON buildings to the app's existing UCLA map
# coordinates. Keeping that coordinate frame preserves all event pins/routes.
LON0, LAT0 = -118.45, 34.0677
X_MEAN, Y_MEAN = 633.1120646903511, 428.0610513587225
X_COEF = (0.6683980492545151, -0.00014539649707329268, 828.16)
Y_COEF = (-0.0006889092778114415, -0.6423538741923989, 549.72)
RADIUS = 6378137
COS_LAT = math.cos(math.radians(LAT0))

BG = "#f5f4ed"
ROAD = "#777676"


def xy(point):
    lon, lat = point[:2]
    mx = (lon - LON0) * math.pi / 180 * RADIUS * COS_LAT
    my = (lat - LAT0) * math.pi / 180 * RADIUS
    dx, dy = mx - X_MEAN, my - Y_MEAN
    return (X_COEF[0] * dx + X_COEF[1] * dy + X_COEF[2],
            Y_COEF[0] * dx + Y_COEF[1] * dy + Y_COEF[2])


def fmt(value):
    return f"{value:.1f}".rstrip("0").rstrip(".")


def line_path(lines):
    parts = []
    for line in lines:
        if len(line) < 2:
            continue
        pts = [xy(p) for p in line]
        parts.append("M" + fmt(pts[0][0]) + " " + fmt(pts[0][1]) +
                     " L" + " L".join(fmt(x) + " " + fmt(y) for x, y in pts[1:]))
    return " ".join(parts)


def polygon_path(polygons):
    parts = []
    for polygon in polygons:
        for ring in polygon:
            if len(ring) < 3:
                continue
            pts = [xy(p) for p in ring]
            parts.append("M" + fmt(pts[0][0]) + " " + fmt(pts[0][1]) +
                         " L" + " L".join(fmt(x) + " " + fmt(y) for x, y in pts[1:]) + " Z")
    return " ".join(parts)


def representative_point(polygons):
    # Use the centroid of the largest outer ring (building footprints are
    # generally compact); this point is also useful for placing its map pin.
    rings = [poly[0] for poly in polygons if poly and len(poly[0]) >= 3]
    ring = max(rings, key=lambda r: abs(ring_area(r)))
    pts = [xy(p) for p in ring]
    area = 0
    cx = cy = 0
    for i, (x, y) in enumerate(pts):
        x2, y2 = pts[(i + 1) % len(pts)]
        cross = x * y2 - x2 * y
        area += cross
        cx += (x + x2) * cross
        cy += (y + y2) * cross
    if abs(area) < 1e-8:
        return sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)
    center = (cx / (3 * area), cy / (3 * area))
    if inside_ring(center, pts):
        return center
    # For concave footprints whose centroid falls outside, find an interior
    # point on a horizontal scanline, preferring the widest interior segment.
    min_y, max_y = min(y for _, y in pts), max(y for _, y in pts)
    best = None
    for step in range(1, 100):
        y = min_y + (max_y - min_y) * step / 100
        xs = []
        for i, (x1, y1) in enumerate(pts):
            x2, y2 = pts[(i + 1) % len(pts)]
            if (y1 > y) != (y2 > y):
                xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            width = xs[i + 1] - xs[i]
            if best is None or width > best[0]:
                best = (width, (xs[i] + xs[i + 1]) / 2, y)
    return (best[1], best[2]) if best else center


def inside_ring(point, ring):
    x, y = point
    inside = False
    for i, (x1, y1) in enumerate(ring):
        x2, y2 = ring[(i + 1) % len(ring)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def ring_area(ring):
    pts = [xy(p) for p in ring]
    return sum(pts[i][0] * pts[(i + 1) % len(pts)][1] -
               pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts))) / 2


def render():
    buildings = json.loads(BUILDINGS.read_text())["features"]
    roads = json.loads(ROADS.read_text())["features"]
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}">',
           f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{BG}"/>',
           '<g fill="none" stroke-linecap="round" stroke-linejoin="round">']

    # Fine paths and campus streets share the coffee palette, with clear weight hierarchy.
    road_width = {"footway": 0.65, "steps": 0.55, "path": 0.6, "pedestrian": 1.0,
                  "service": 1.1, "cycleway": 0.75, "tertiary": 1.55,
                  "secondary": 1.85, "secondary_link": 1.45,
                  "unclassified": 1.25, "residential": 1.35, "living_street": 1.15}
    for feature in roads:
        geometry = feature.get("geometry") or {}
        kind = geometry.get("type")
        if kind == "MultiLineString":
            lines = geometry["coordinates"]
        elif kind == "LineString":
            lines = [geometry["coordinates"]]
        else:
            continue
        d = line_path(lines)
        if d:
            highway = feature.get("properties", {}).get("highway", "footway")
            width = road_width.get(highway, 0.85)
            opacity = ".84" if highway in {"footway", "steps", "path"} else ".94"
            svg.append(f'<path d="{d}" stroke="{ROAD}" stroke-width="{width}" opacity="{opacity}"/>')
    svg.append('</g></svg>')
    building_index = {}
    for feature in buildings:
        geometry = feature.get("geometry") or {}
        kind = geometry.get("type")
        if kind == "MultiPolygon":
            polygons = geometry["coordinates"]
        elif kind == "Polygon":
            polygons = [geometry["coordinates"]]
        else:
            continue
        d = polygon_path(polygons)
        if d:
            building_id = str(feature.get("properties", {}).get("full_id", ""))
            name = (feature.get("properties", {}).get("name") or
                    feature.get("properties", {}).get("name:en") or "")
            px, py = representative_point(polygons)
            if building_id:
                building_index[building_id] = {"name": name, "d": d, "x": round(px, 2), "y": round(py, 2)}
    OUTPUT.write_text("\n".join(svg))
    BUILDING_INDEX.write_text("window.CAMPUS_BUILDINGS=" + json.dumps(building_index, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes), {len(buildings)} buildings, {len(roads)} road/path features")


if __name__ == "__main__":
    render()
