"""Coordinate per i piccoli grafici SVG disegnati nei template."""

import math

MONTHS = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]


def radar_chart(axes, size=320, pad=50, side=110):
    """axes: [(nome, valore 0-100)] -> dati per un grafico radar SVG (margini laterali per le etichette)."""
    c = size / 2 + side
    cy = size / 2
    r = size / 2 - pad
    n = len(axes)
    out = {"width": size + 2 * side, "height": size, "c": c, "cy": cy, "rings": [], "spokes": [], "labels": [], "points": ""}
    for frac in (0.25, 0.5, 0.75, 1):
        pts = []
        for i in range(n):
            a = -math.pi / 2 + 2 * math.pi * i / n
            pts.append(f"{c + r * frac * math.cos(a):.1f},{cy + r * frac * math.sin(a):.1f}")
        out["rings"].append(" ".join(pts))
    pts = []
    for i, (name, v) in enumerate(axes):
        a = -math.pi / 2 + 2 * math.pi * i / n
        x, y = c + r * math.cos(a), cy + r * math.sin(a)
        out["spokes"].append((round(x, 1), round(y, 1)))
        lx, ly = c + (r + 16) * math.cos(a), cy + (r + 16) * math.sin(a)
        anchor = "middle" if abs(math.cos(a)) < 0.3 else ("start" if math.cos(a) > 0 else "end")
        out["labels"].append((round(lx, 1), round(ly + 4, 1), anchor, name, v))
        pv = r * v / 100
        pts.append(f"{c + pv * math.cos(a):.1f},{cy + pv * math.sin(a):.1f}")
    out["points"] = " ".join(pts)
    return out


def step_chart(timeline, label, width=720, height=220, pad_l=44, pad_b=28, pad_t=16, pad_r=16):
    """timeline: [(data, indice_categoria, coefficiente)] -> grafico a gradini della categoria."""
    cats = [c for _, c, _ in timeline]
    lo, hi = min(cats) - 1, max(cats) + 1
    n = len(timeline)
    iw, ih = width - pad_l - pad_r, height - pad_t - pad_b

    def x(i):
        return pad_l + iw * i / max(1, n - 1)

    def y(c):
        return pad_t + ih * (hi - c) / max(1, hi - lo)

    path = []
    for i, (_, c, _) in enumerate(timeline):
        if i == 0:
            path.append(f"M{x(i):.1f},{y(c):.1f}")
        else:
            path.append(f"H{x(i):.1f}V{y(c):.1f}")
    return {
        "width": width, "height": height, "path": " ".join(path),
        "yticks": [(round(y(c), 1), label(c)) for c in range(lo, hi + 1)],
        "points": [(round(x(i), 1), round(y(c), 1), d, label(c), coef, MONTHS[d.month - 1] + " " + str(d.year)[2:]) for i, (d, c, coef) in enumerate(timeline)],
        "pad_l": pad_l, "right": width - pad_r, "bottom": height - pad_b,
    }
