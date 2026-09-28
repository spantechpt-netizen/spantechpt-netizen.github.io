"""
Plain 2-D geometry on {x, y} points and polygons (arrays of points, first
vertex not repeated). Everything is in millimetres in the slab plane.

Port of `shopdrawings/lib/geometry.mjs`, plus the small helpers every other module shares (`js_round`, `fmt_num`,
`to_fixed`, `ceil_to`, `unit`, `perp`, `add`, `mid`, `dist_to_seg`, `DrawingsError`).
"""
import math
import re
from decimal import Decimal, ROUND_HALF_UP

EPS = 1e-6


class DrawingsError(Exception):
    """The error every module raises where the JS does `throw new Error(msg)`."""


# ------------------------------------------------------------------ JS number helpers (shared by every module)
def js_round(x):
    """JS `Math.round`: rounds half up (towards +Infinity): Math.round(2.5) === 3, Math.round(-2.5) === -2."""
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return x
    return int(math.floor(x + 0.5))


def js_hypot(*vals):
    """JS `Math.hypot` as V8 computes it (values scaled by the largest, Kahan summation): the last bit can differ
    from Python's correctly rounded `math.hypot`, so every distance goes through this one to match the Node output."""
    if not vals:
        return 0
    one_nan = False
    m = 0.0
    absv = []
    for v in vals:
        v = float(v)
        if math.isnan(v):
            one_nan = True
            absv.append(0.0)
        else:
            a = abs(v)
            absv.append(a)
            if a > m:
                m = a
    if m == math.inf:
        return math.inf
    if one_nan:
        return math.nan
    if m == 0:
        return 0
    s = 0.0
    comp = 0.0
    for a in absv:
        n = a / m
        summand = n * n - comp
        prelim = s + summand
        comp = (prelim - s) - summand
        s = prelim
    return math.sqrt(s) * m


def fmt_num(v):
    """JS `String(number)`: a whole number prints without `.0`, otherwise the shortest round-trip representation."""
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    if v is None:
        return 'null'
    v = float(v)
    if math.isnan(v):
        return 'NaN'
    if math.isinf(v):
        return 'Infinity' if v > 0 else '-Infinity'
    if v == 0:
        return '0'  # String(-0) === '0'
    if v == int(v) and abs(v) < 1e21:
        return str(int(v))
    s = repr(v)
    if 'e' in s:
        mant, exp = s.split('e')
        ex = int(exp)
        if -7 < ex < 21:
            # JS prints these positionally (repr uses an exponent below 1e-4 and above 1e16)
            s = format(Decimal(s), 'f')
        else:
            s = mant + 'e' + ('+' if ex > 0 else '-') + str(abs(ex))
    return s


def to_fixed(v, n):
    """JS `Number.prototype.toFixed(n)`: fixed decimals, ties rounded away from zero on the exact binary value."""
    if isinstance(v, bool) or v is None:
        v = 1 if v else 0
    v = float(v)
    if math.isnan(v):
        return 'NaN'
    if math.isinf(v):
        return 'Infinity' if v > 0 else '-Infinity'
    q = Decimal(1).scaleb(-n) if n else Decimal(1)
    d = Decimal(v).quantize(q, rounding=ROUND_HALF_UP)
    return format(d, 'f')  # (-0.0001).toFixed(2) === '-0.00' in JS; Decimal keeps that sign too


def dist(a, b):
    return js_hypot(a['x'] - b['x'], a['y'] - b['y'])


def bbox(points):
    min_x, min_y, max_x, max_y = math.inf, math.inf, -math.inf, -math.inf
    for p in points:
        if p['x'] < min_x:
            min_x = p['x']
        if p['y'] < min_y:
            min_y = p['y']
        if p['x'] > max_x:
            max_x = p['x']
        if p['y'] > max_y:
            max_y = p['y']
    return {'minX': min_x, 'minY': min_y, 'maxX': max_x, 'maxY': max_y, 'w': max_x - min_x, 'h': max_y - min_y,
            'cx': (min_x + max_x) / 2, 'cy': (min_y + max_y) / 2}


def union_bbox(a, b):
    if not a:
        return b
    if not b:
        return a
    return bbox([{'x': a['minX'], 'y': a['minY']}, {'x': a['maxX'], 'y': a['maxY']},
                 {'x': b['minX'], 'y': b['minY']}, {'x': b['maxX'], 'y': b['maxY']}])


def expand_bbox(b, m):
    return bbox([{'x': b['minX'] - m, 'y': b['minY'] - m}, {'x': b['maxX'] + m, 'y': b['maxY'] + m}])


def bbox_contains(b, p):
    return p['x'] >= b['minX'] - EPS and p['x'] <= b['maxX'] + EPS and p['y'] >= b['minY'] - EPS and p['y'] <= b['maxY'] + EPS


def polygon_area(poly):
    """Signed area (positive when counter-clockwise)."""
    a = 0
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        a += p['x'] * q['y'] - q['x'] * p['y']
    return a / 2


def centroid(poly):
    a = polygon_area(poly)
    if abs(a) < EPS:
        return bbox(poly)
    cx = 0
    cy = 0
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        f = p['x'] * q['y'] - q['x'] * p['y']
        cx += (p['x'] + q['x']) * f
        cy += (p['y'] + q['y']) * f
    return {'x': cx / (6 * a), 'y': cy / (6 * a)}


def point_in_polygon(pt, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        a, b = poly[i], poly[j]
        if (a['y'] > pt['y']) != (b['y'] > pt['y']) and pt['x'] < ((b['x'] - a['x']) * (pt['y'] - a['y'])) / (b['y'] - a['y']) + a['x']:
            inside = not inside
        j = i
    return inside


def perimeter(poly):
    l = 0
    n = len(poly)
    for i in range(n):
        l += dist(poly[i], poly[(i + 1) % n])
    return l


def edges(poly):
    """Polygon edges as [{a, b, length, dx, dy}]."""
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        out.append({'a': a, 'b': b, 'length': dist(a, b), 'dx': b['x'] - a['x'], 'dy': b['y'] - a['y']})
    return out


def clean_polygon(poly):
    """Remove a duplicated closing vertex and collinear repeats."""
    pts = [p for i, p in enumerate(poly) if i == 0 or dist(p, poly[i - 1]) > 0.5]
    if len(pts) > 1 and dist(pts[0], pts[-1]) < 0.5:
        pts.pop()
    return pts


def simplify_polygon(poly, tol=1):
    """Drop vertices that lie on the straight line between their neighbours (within tol mm)."""
    pts = clean_polygon(poly)
    if len(pts) < 4:
        return pts
    out = []
    n = len(pts)
    for i in range(n):
        a, p, b = pts[(i + n - 1) % n], pts[i], pts[(i + 1) % n]
        length = dist(a, b)
        off = 0 if length < 1e-9 else abs((b['x'] - a['x']) * (a['y'] - p['y']) - (a['x'] - p['x']) * (b['y'] - a['y'])) / length
        if off > tol:
            out.append(p)
    return out if len(out) >= 3 else pts


def as_axis_rect(poly, tol=1):
    """If the polygon is an axis-aligned rectangle, return it as {x, y, w, h}."""
    pts = clean_polygon(poly)
    if len(pts) != 4:
        return None
    b = bbox(pts)
    for p in pts:
        on_x = abs(p['x'] - b['minX']) < tol or abs(p['x'] - b['maxX']) < tol
        on_y = abs(p['y'] - b['minY']) < tol or abs(p['y'] - b['maxY']) < tol
        if not on_x or not on_y:
            return None
    return {'x': b['minX'], 'y': b['minY'], 'w': b['w'], 'h': b['h']}


def rect_polygon(r):
    x, y, w, h = r['x'], r['y'], r['w'], r['h']
    return [{'x': x, 'y': y}, {'x': x + w, 'y': y}, {'x': x + w, 'y': y + h}, {'x': x, 'y': y + h}]


def rect_center(r):
    return {'x': r['x'] + r['w'] / 2, 'y': r['y'] + r['h'] / 2}


def grow_rect(r, m):
    return {'x': r['x'] - m, 'y': r['y'] - m, 'w': r['w'] + 2 * m, 'h': r['h'] + 2 * m}


def circle_polygon(cx, cy, r, n=32):
    out = []
    for i in range(n):
        t = (i / n) * math.pi * 2
        out.append({'x': cx + r * math.cos(t), 'y': cy + r * math.sin(t)})
    return out


def chords_at_y(poly, Y):
    """Horizontal chords [x1, x2] where the line y = Y crosses the polygon (even-odd)."""
    xs = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if abs(a['y'] - b['y']) < EPS:
            continue
        if (a['y'] <= Y and b['y'] > Y) or (b['y'] <= Y and a['y'] > Y):
            xs.append(a['x'] + ((Y - a['y']) * (b['x'] - a['x'])) / (b['y'] - a['y']))
    xs.sort()
    out = []
    i = 0
    while i + 1 < len(xs):
        if xs[i + 1] - xs[i] > 1:
            out.append([xs[i], xs[i + 1]])
        i += 2
    return out


def chords_at_x(poly, X):
    """Vertical chords [y1, y2] where the line x = X crosses the polygon."""
    return chords_at_y([{'x': p['y'], 'y': p['x']} for p in poly], X)


def subtract_intervals(intervals, cuts):
    """Subtract cut intervals from a list of [a, b] intervals."""
    out = [list(i) for i in intervals]
    for c1, c2 in cuts:
        if c2 - c1 <= 0:
            continue
        nxt = []
        for a, b in out:
            if c2 <= a or c1 >= b:
                nxt.append([a, b])
                continue
            if c1 > a:
                nxt.append([a, c1])
            if c2 < b:
                nxt.append([c2, b])
        out = nxt
    return [ab for ab in out if ab[1] - ab[0] > 1]


def round_to(v, step=1):
    """JS `round(v, step)` (the export is named `round` there; renamed so it does not shadow the Python builtin)."""
    return js_round(v / step) * step


def ceil_to(v, step=1):
    return math.ceil(v / step - 1e-9) * step


def transform_point(p, t):
    """Transform a point by an INSERT-style scale / rotation (degrees) / translation."""
    r = ((t.get('rotation') or 0) * math.pi) / 180
    sx = t.get('sx') if t.get('sx') is not None else 1
    sy = t.get('sy') if t.get('sy') is not None else 1
    x, y = p['x'] * sx, p['y'] * sy
    return {
        'x': (t.get('x') or 0) + x * math.cos(r) - y * math.sin(r),
        'y': (t.get('y') or 0) + x * math.sin(r) + y * math.cos(r),
    }


def clip_segment_to_polygon(a, b, poly):
    """Clip segment a-b to the inside of a polygon; returns the sub-segments that lie inside."""
    ts = [0, 1]
    n = len(poly)
    dx, dy = b['x'] - a['x'], b['y'] - a['y']
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        ex, ey = q['x'] - p['x'], q['y'] - p['y']
        den = dx * ey - dy * ex
        if abs(den) < 1e-9:
            continue
        t = ((p['x'] - a['x']) * ey - (p['y'] - a['y']) * ex) / den
        u = ((p['x'] - a['x']) * dy - (p['y'] - a['y']) * dx) / den
        if t > 0 and t < 1 and u >= 0 and u <= 1:
            ts.append(t)
    ts.sort()
    out = []
    for i in range(len(ts) - 1):
        t0, t1 = ts[i], ts[i + 1]
        if t1 - t0 < 1e-6:
            continue
        m = {'x': a['x'] + dx * (t0 + t1) / 2, 'y': a['y'] + dy * (t0 + t1) / 2}
        if point_in_polygon(m, poly):
            out.append([{'x': a['x'] + dx * t0, 'y': a['y'] + dy * t0}, {'x': a['x'] + dx * t1, 'y': a['y'] + dy * t1}])
    return out


def clip_polyline_to_polygon(pts, poly, tol=0):
    """
    The longest run of a polyline inside a polygon (points within `tol` of the boundary count as inside), cut exactly
    where it leaves: `{ pts, from, to, cutStart, cutEnd }` with `from` / `to` the indices of the first and last
    original points kept, the cut points added at the ends, and the flags saying which ends are cuts. None when
    nothing lies inside.
    """
    if not pts or len(pts) < 2 or not poly or len(poly) < 3:
        return None

    def inside(q):
        return point_in_polygon(q, poly) or (tol > 0 and dist_to_polygon(q, poly) <= tol)

    def crossing(a, b):
        # the piece of a->b inside the polygon that touches a: its far end is where the polyline leaves
        pieces = clip_segment_to_polygon(a, b, poly)
        piece = next((seg for seg in pieces if js_hypot(seg[0]['x'] - a['x'], seg[0]['y'] - a['y']) < 1), None)
        if piece is None:
            pieces.sort(key=lambda u: js_hypot(u[0]['x'] - a['x'], u[0]['y'] - a['y']))
            piece = pieces[0] if pieces else None
        return piece[1] if piece else a

    runs = []
    run = None
    for i in range(len(pts)):
        if inside(pts[i]):
            if not run:
                run = {'from': i, 'to': i, 'cutStart': i > 0}
            run['to'] = i
        elif run:
            run['cutEnd'] = True
            runs.append(run)
            run = None
    if run:
        run['cutEnd'] = False
        runs.append(run)
    if not runs:
        return None

    def span(r):
        L = 0
        for i in range(r['from'], r['to']):
            L += js_hypot(pts[i + 1]['x'] - pts[i]['x'], pts[i + 1]['y'] - pts[i]['y'])
        return L

    runs.sort(key=lambda r: -span(r))
    best = runs[0]
    out = pts[best['from']:best['to'] + 1]
    cut_start = False
    cut_end = False
    if best['cutStart']:
        c = crossing(pts[best['from']], pts[best['from'] - 1])
        if js_hypot(c['x'] - out[0]['x'], c['y'] - out[0]['y']) > 1:
            out.insert(0, c)
        cut_start = True
    if best['cutEnd']:
        c = crossing(pts[best['to']], pts[best['to'] + 1])
        if js_hypot(c['x'] - out[-1]['x'], c['y'] - out[-1]['y']) > 1:
            out.append(c)
        cut_end = True
    return {'pts': out, 'from': best['from'], 'to': best['to'], 'cutStart': cut_start, 'cutEnd': cut_end}


def dist_to_polygon(p, poly):
    """Distance from a point to the boundary of a polygon."""
    best = math.inf
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        dx, dy = b['x'] - a['x'], b['y'] - a['y']
        l2 = dx * dx + dy * dy
        t = max(0, min(1, ((p['x'] - a['x']) * dx + (p['y'] - a['y']) * dy) / l2)) if l2 else 0
        best = min(best, js_hypot(p['x'] - (a['x'] + t * dx), p['y'] - (a['y'] + t * dy)))
    return best


# ------------------------------------------------------------------ shared point helpers (from design.mjs)
def mid(a, b):
    return {'x': (a['x'] + b['x']) / 2, 'y': (a['y'] + b['y']) / 2}


def unit(a, b):
    L = dist(a, b) or 1
    return {'x': (b['x'] - a['x']) / L, 'y': (b['y'] - a['y']) / L}


def perp(u):
    return {'x': -u['y'], 'y': u['x']}


def add(p, u, k):
    return {'x': p['x'] + u['x'] * k, 'y': p['y'] + u['y'] * k}


def dist_to_seg(p, a, b):
    """Distance from a point to a segment."""
    L2 = (b['x'] - a['x']) ** 2 + (b['y'] - a['y']) ** 2
    if L2 < 1e-9:
        return dist(p, a)
    t = max(0, min(1, ((p['x'] - a['x']) * (b['x'] - a['x']) + (p['y'] - a['y']) * (b['y'] - a['y'])) / L2))
    return dist(p, {'x': a['x'] + t * (b['x'] - a['x']), 'y': a['y'] + t * (b['y'] - a['y'])})
