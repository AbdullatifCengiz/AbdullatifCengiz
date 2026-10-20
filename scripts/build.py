#!/usr/bin/env python3
"""Builds every image on the profile and refreshes the README activity block.

    python scripts/build.py            # live data (needs GH_TOKEN)
    python scripts/build.py --sample   # offline preview with made-up numbers
"""
import datetime as dt
import html
import json
import os
import random
import re
import sys
import urllib.request
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
CONFIG = json.loads((ROOT / "profile" / "config.json").read_text(encoding="utf-8"))
USER = CONFIG["username"]

C = {
    "ink": "#0B0E13",
    "panel": "#121821",
    "panel2": "#171E29",
    "line": "#232C38",
    "grid": "#18202A",
    "text": "#EDF1F6",
    "soft": "#B4BFCC",
    "muted": "#7D8A9B",
    "amber": "#FFB224",
    "amber_dim": "#7A5614",
    "teal": "#3DD6C3",
}
TONES = {"amber": C["amber"], "teal": C["teal"], "muted": C["muted"]}

MOTION_OFF = "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"


def num(n):
    s = f"{n:.1f}"
    return s[:-2] if s.endswith(".0") else s


class Face:
    def __init__(self, filename):
        self.font = TTFont(ASSETS / "fonts" / filename)
        self.glyphs = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        self.upm = self.font["head"].unitsPerEm
        self.hmtx = self.font["hmtx"]

    def glyph(self, ch):
        name = self.cmap.get(ord(ch))
        if name is None:
            raise ValueError(f"glyph missing for {ch!r}")
        return name

    def width(self, s, size, tracking=0.0):
        if not s:
            return 0.0
        scale = size / self.upm
        return sum(self.hmtx[self.glyph(c)][0] * scale for c in s) + tracking * (len(s) - 1)

    def path(self, s, size, x, y, tracking=0.0):
        pen = SVGPathPen(self.glyphs, ntos=num)
        scale = size / self.upm
        cx = x
        for ch in s:
            name = self.glyph(ch)
            self.glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, cx, y)))
            cx += self.hmtx[name][0] * scale + tracking
        return pen.getCommands()


F = {
    "display": Face("display-bold.woff"),
    "text": Face("text-medium.woff"),
    "semi": Face("text-semibold.woff"),
    "mono": Face("mono.woff"),
    "monob": Face("mono-bold.woff"),
}


def T(s, face, size, x, y, fill, anchor="start", tracking=0.0, extra=""):
    f = F[face]
    w = f.width(s, size, tracking)
    if anchor == "middle":
        x -= w / 2
    elif anchor == "end":
        x -= w
    d = f.path(s, size, x, y, tracking)
    return f'<path d="{d}" fill="{fill}" {extra}/>' if d else ""


def W(s, face, size, tracking=0.0):
    return F[face].width(s, size, tracking)


def wrap(s, face, size, max_w):
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if W(trial, face, size) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def doc(w, h, title, body, css=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{html.escape(title)}"><title>{html.escape(title)}</title>'
        f"<style>{css}{MOTION_OFF}</style>{body}</svg>"
    )


def chip(label, x, y, face="mono", size=11, color=None, fill="none", pad=11, h=24, tracking=0.6, dot=None):
    color = color or C["soft"]
    tw = W(label, face, size, tracking)
    dot_w = 12 if dot else 0
    w = tw + pad * 2 + dot_w
    out = f'<rect x="{num(x)}" y="{num(y)}" width="{num(w)}" height="{h}" rx="7" fill="{fill}" stroke="{C["line"]}"/>'
    if dot:
        out += f'<circle cx="{num(x + pad + 3)}" cy="{num(y + h / 2)}" r="3" fill="{dot}"/>'
    out += T(label, face, size, x + pad + dot_w, y + h / 2 + size * 0.36, color, tracking=tracking)
    return out, w


def dot_grid(w, h, pid="g"):
    return (
        f'<defs><pattern id="{pid}" width="22" height="22" patternUnits="userSpaceOnUse">'
        f'<circle cx="1" cy="1" r="1" fill="{C["grid"]}"/></pattern></defs>'
        f'<rect width="{w}" height="{h}" rx="18" fill="{C["ink"]}"/>'
        f'<rect width="{w}" height="{h}" rx="18" fill="url(#{pid})"/>'
    )


# ---------------------------------------------------------------- header

def build_header(now):
    w, h = 1000, 420
    b = [dot_grid(w, h)]
    b.append(
        '<defs><radialGradient id="glow" cx="78%" cy="40%" r="45%">'
        f'<stop offset="0" stop-color="{C["amber"]}" stop-opacity=".10"/>'
        f'<stop offset="1" stop-color="{C["amber"]}" stop-opacity="0"/></radialGradient>'
        '<filter id="blur" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="3"/></filter></defs>'
        f'<rect width="{w}" height="{h}" rx="18" fill="url(#glow)"/>'
    )

    x0 = 48
    b.append(T("▸ " + CONFIG["location_line"], "mono", 13, x0, 66, C["muted"], tracking=0.4))
    first, last = CONFIG["name"]
    b.append(f'<g class="rise">{T(first, "display", 80, x0 - 3, 152, C["text"], tracking=-2.2)}</g>')
    b.append(f'<g class="rise d2">{T(last, "display", 80, x0 - 3, 232, C["amber"], tracking=-2.2)}</g>')
    caret_x = x0 - 3 + W(last, "display", 80, -2.2) + 10
    b.append(f'<rect class="caret" x="{num(caret_x)}" y="176" width="9" height="58" rx="2" fill="{C["amber"]}"/>')
    for i, line in enumerate(CONFIG["intro"]):
        b.append(T(line, "text", 17, x0, 284 + i * 27, C["soft"]))
    cx = x0
    for label in CONFIG["chips"]:
        part, cw = chip(label, cx, 334, tracking=1.2)
        b.append(part)
        cx += cw + 8

    b.append(build_pipeline())

    b.append(f'<line x1="32" y1="378" x2="{w - 32}" y2="378" stroke="{C["line"]}"/>')
    b.append(T("now →  " + "  ·  ".join(CONFIG["now"]), "mono", 12, x0, 404, C["muted"], tracking=0.4))
    b.append(T(f"build {now:%Y.%m.%d}", "mono", 12, w - 48, 404, C["muted"], anchor="end", tracking=0.4))

    css = (
        f".rise{{animation:rise .9s cubic-bezier(.2,.8,.2,1) both}}.d2{{animation-delay:.15s}}"
        "@keyframes rise{from{opacity:0;transform:translateY(14px)}}"
        ".caret{animation:blink 1.1s steps(1) infinite}@keyframes blink{50%{opacity:0}}"
        ".led{animation:led 1.6s steps(1) infinite}@keyframes led{50%{opacity:.15}}"
        ".flow{stroke-dasharray:4 10;animation:flow 1.2s linear infinite}@keyframes flow{to{stroke-dashoffset:-28}}"
        ".bar{transform-box:fill-box;transform-origin:bottom;animation:grow 2.6s ease-in-out infinite alternate}"
        "@keyframes grow{from{transform:scaleY(.25)}}"
        ".alert{animation:alert 3s ease-in-out infinite}@keyframes alert{0%,40%{opacity:0}55%,90%{opacity:1}100%{opacity:0}}"
        ".srv{animation:led 2.2s steps(1) infinite}"
    )
    return doc(w, h, f"{first} {last} — header", "".join(b), css)


def build_pipeline():
    a, t, m, line, panel = C["amber"], C["teal"], C["muted"], C["line"], C["panel"]
    out = []
    out.append(T("SIGNAL PATH", "mono", 10, 612, 58, m, tracking=2))
    trace1 = "M 690 112 H 838"
    trace2 = "M 914 104 H 940 V 196 H 820 V 218"
    for i, d in enumerate((trace1, trace2)):
        out.append(f'<path id="tr{i}" d="{d}" fill="none" stroke="{line}" stroke-width="2"/>')
        out.append(f'<path class="flow" d="{d}" fill="none" stroke="{a}" stroke-opacity=".55" stroke-width="2"/>')

    cx, cy = 652, 112
    pins = "".join(
        f'<rect x="{cx - 30 + 9 + k * 12}" y="{cy - 38}" width="4" height="7" rx="1" fill="{line}"/>'
        f'<rect x="{cx - 30 + 9 + k * 12}" y="{cy + 31}" width="4" height="7" rx="1" fill="{line}"/>'
        for k in range(4)
    )
    out.append(pins)
    out.append(f'<rect x="{cx - 32}" y="{cy - 32}" width="64" height="64" rx="8" fill="{panel}" stroke="{line}" stroke-width="1.5"/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="16" fill="none" stroke="{t}" stroke-width="2"/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="7" fill="{t}" fill-opacity=".35"/>')
    out.append(f'<circle cx="{cx + 3}" cy="{cy - 3}" r="2" fill="{C["text"]}" fill-opacity=".8"/>')
    out.append(f'<circle class="led" cx="{cx + 22}" cy="{cy - 22}" r="3" fill="{a}"/>')
    out.append(T("cam · esp32", "mono", 11, cx, cy + 58, m, anchor="middle"))

    sx, sy = 838, 84
    for k in range(3):
        y = sy + k * 20
        out.append(f'<rect x="{sx}" y="{y}" width="76" height="15" rx="4" fill="{panel}" stroke="{line}" stroke-width="1.5"/>')
        out.append(f'<circle class="srv" style="animation-delay:{k * .7:.1f}s" cx="{sx + 10}" cy="{y + 7.5}" r="2.5" fill="{t}"/>')
        out.append(f'<rect x="{sx + 22}" y="{y + 6}" width="{30 - k * 6}" height="3" rx="1.5" fill="{line}"/>')
    out.append(T("api · laravel", "mono", 11, sx + 38, sy + 78, m, anchor="middle"))

    px, py, pw, ph = 612, 218, 352, 138
    out.append(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="10" fill="{panel}" stroke="{line}" stroke-width="1.5"/>')
    out.append(f'<line x1="{px}" y1="{py + 26}" x2="{px + pw}" y2="{py + 26}" stroke="{line}"/>')
    for k, col in enumerate(("#3A4452", "#3A4452", "#3A4452")):
        out.append(f'<circle cx="{px + 16 + k * 13}" cy="{py + 13}" r="4" fill="{col}"/>')
    out.append(T("plaka-takip / live", "mono", 10, px + pw / 2, py + 17, m, anchor="middle", tracking=0.4))

    plx, ply, plw, plh = px + 18, py + 44, 150, 36
    out.append(f'<clipPath id="type"><rect x="{plx}" y="{ply}" width="{plw}" height="{plh}">'
               f'<animate attributeName="width" values="0;{plw};{plw};0" keyTimes="0;.35;.9;1" dur="6s" repeatCount="indefinite"/></rect></clipPath>')
    out.append(f'<rect x="{plx}" y="{ply}" width="{plw}" height="{plh}" rx="5" fill="#0F141B" stroke="{line}" stroke-dasharray="3 4"/>')
    out.append(f'<g clip-path="url(#type)"><rect x="{plx}" y="{ply}" width="{plw}" height="{plh}" rx="5" fill="#E9EEF4"/>'
               f'<rect x="{plx}" y="{ply}" width="20" height="{plh}" rx="5" fill="#1F4FBF"/>'
               f'<rect x="{plx + 12}" y="{ply}" width="8" height="{plh}" fill="#1F4FBF"/>'
               + T("TR", "monob", 8, plx + 10, ply + plh - 6, "#FFFFFF", anchor="middle")
               + T("23 FL 026", "monob", 17, plx + 28, ply + 24, "#0B0E13", tracking=0.6) + "</g>")
    out.append(f'<g class="alert">{T("unknown plate → alert sent", "mono", 10, plx, ply + plh + 22, a)}</g>')

    bx, base = px + 214, py + 112
    heights = [22, 38, 30, 54, 44, 64, 50]
    for k, bh in enumerate(heights):
        fill = a if k == 5 else "#2B3543"
        out.append(f'<rect class="bar" style="animation-delay:{k * .18:.2f}s" x="{bx + k * 18}" y="{base - bh}" width="11" height="{bh}" rx="2" fill="{fill}"/>')
    out.append(f'<line x1="{bx - 4}" y1="{base + 1}" x2="{bx + 7 * 18}" y2="{base + 1}" stroke="{line}"/>')
    out.append(f'<circle class="led" cx="{px + 22}" cy="{py + ph - 14}" r="3" fill="{t}"/>')
    out.append(T("live", "mono", 10, px + 30, py + ph - 10.5, t, tracking=0.6))

    for i, delay in ((0, 0), (0, 1.2), (1, 0.6)):
        out.append(f'<g><circle r="6" fill="{a}" fill-opacity=".45" filter="url(#blur)"/><circle r="3" fill="{a}"/>'
                   f'<animateMotion dur="2.4s" begin="{delay}s" repeatCount="indefinite"><mpath xlink:href="#tr{i}"/></animateMotion></g>')
    return "".join(out)


# ---------------------------------------------------------------- skyline

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def build_skyline(data):
    w, h = 1000, 330
    ground, river_h = 244, 62
    rnd = random.Random(7)
    weeks = data["weeks"][-53:]
    totals = [sum(d["count"] for d in wk) for wk in weeks]
    peak = max(totals) or 1
    b = []
    b.append(
        '<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#06090E"/><stop offset=".72" stop-color="#101827"/>'
        '<stop offset="1" stop-color="#1F1A14"/></linearGradient>'
        '<linearGradient id="fade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".9"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        f'<mask id="refl"><rect x="0" y="{ground}" width="{w}" height="{river_h}" fill="url(#fade)"/></mask>'
        '<mask id="moon"><rect width="1000" height="330" fill="#fff"/><circle cx="893" cy="62" r="17" fill="#000"/></mask>'
        f'<clipPath id="card"><rect width="{w}" height="{h}" rx="18"/></clipPath></defs>'
    )
    b.append('<g clip-path="url(#card)">')
    b.append(f'<rect width="{w}" height="{h}" fill="url(#sky)"/>')
    for _ in range(80):
        x, y = rnd.uniform(10, w - 10), rnd.uniform(10, ground - 70)
        r = rnd.choice((.6, .8, 1, 1.3))
        tw = f' class="tw" style="animation-delay:{rnd.uniform(0, 5):.1f}s"' if rnd.random() < .35 else ""
        b.append(f'<circle{tw} cx="{x:.0f}" cy="{y:.0f}" r="{r}" fill="#D7E0EA" fill-opacity="{rnd.uniform(.25, .8):.2f}"/>')
    b.append('<circle cx="880" cy="70" r="20" fill="#F2E6CC" mask="url(#moon)"/>')

    b.append(T("ELAZIĞ · BUILT ONE COMMIT AT A TIME", "mono", 12, 40, 46, C["muted"], tracking=1.6))
    b.append(T(f"{data['total']:,} contributions", "display", 30, 39, 84, C["text"], tracking=-0.6))
    sub = f"last 52 weeks  ·  busiest week {peak}  ·  current streak {data['streak']}d"
    b.append(T(sub, "mono", 12, 40, 107, C["soft"], tracking=0.3))

    city = []
    city.append(f'<path d="M 0 {ground} C 40 {ground - 18}, 70 {ground - 36}, 124 {ground - 38} S 212 {ground - 24}, 246 {ground} Z" fill="#0D121A"/>')
    city.append(castle(56, ground - 80))
    left, right = 250, 978
    step = (right - left) / len(weeks)
    bw = step * .72
    tallest = totals.index(peak)
    windows, reflections = [], []
    for i, total in enumerate(totals):
        x = left + i * step
        if total == 0:
            city.append(f'<rect x="{x:.1f}" y="{ground - 4}" width="{bw:.1f}" height="4" fill="#141B25"/>')
            continue
        bh = 10 + (total / peak) ** .7 * 108
        top = ground - bh
        shade = "#1A2230" if total / peak < .5 else "#1E2736"
        city.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="{shade}"/>')
        city.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bw:.1f}" height="1.5" fill="#2C3748"/>')
        roof = rnd.random()
        if bh > 36 and i != tallest:
            if roof < .28:
                city.append(f'<rect x="{x + bw * .2:.1f}" y="{top - 4:.1f}" width="{bw * .45:.1f}" height="4" fill="{shade}"/>')
            elif roof < .42:
                city.append(f'<line x1="{x + bw * .7:.1f}" y1="{top:.1f}" x2="{x + bw * .7:.1f}" y2="{top - 7:.1f}" stroke="#2C3748"/>')
            elif roof < .52:
                city.append(f'<rect x="{x + bw * .18:.1f}" y="{top - 8:.1f}" width="{bw * .64:.1f}" height="8" fill="{shade}"/>')
        reflections.append(f'<rect x="{x:.1f}" y="{ground}" width="{bw:.1f}" height="{min(bh * .55, river_h):.1f}" fill="{shade}"/>')
        lit = min(.9, .18 + total / peak * .8)
        cols = 2 if bw < 12 else 3
        gap = (bw - cols * 2.2) / (cols + 1)
        wy = top + 6
        while wy < ground - 6:
            for c in range(cols):
                if rnd.random() < lit:
                    wx = x + gap + c * (2.2 + gap)
                    color = C["amber"] if rnd.random() < .7 else "#FFE7B3"
                    cls = f' class="fl" style="animation-delay:{rnd.uniform(0, 9):.1f}s"' if rnd.random() < .08 else ""
                    windows.append(f'<rect{cls} x="{wx:.1f}" y="{wy:.1f}" width="2.2" height="2.8" fill="{color}" fill-opacity=".85"/>')
            wy += 6.5
        if i == tallest:
            ax = x + bw / 2
            city.append(f'<line x1="{ax:.1f}" y1="{top:.1f}" x2="{ax:.1f}" y2="{top - 14:.1f}" stroke="#2C3748" stroke-width="1.5"/>')
            city.append(f'<circle class="beacon" cx="{ax:.1f}" cy="{top - 15:.1f}" r="2.4" fill="#FF6B4A"/>')

    b.append(f'<rect x="0" y="{ground}" width="{w}" height="{h - ground}" fill="#080C12"/>')
    b.append(f'<g mask="url(#refl)" opacity=".35">{"".join(reflections)}</g>')
    for k in range(9):
        y = ground + 10 + k * 6
        x = rnd.uniform(240, 900)
        b.append(f'<rect class="sh" style="animation-delay:{k * .4:.1f}s" x="{x:.0f}" y="{y}" width="{rnd.uniform(20, 70):.0f}" height="1" fill="{C["amber"]}" fill-opacity=".18"/>')
    b.append("".join(city))
    b.append(f'<g>{"".join(windows)}</g>')
    b.append(f'<line x1="0" y1="{ground}" x2="{w}" y2="{ground}" stroke="#263142"/>')

    last_month = None
    for i, wk in enumerate(weeks):
        m = dt.date.fromisoformat(wk[0]["date"]).month
        if m != last_month and 0 < i < len(weeks) - 2:
            b.append(T(MONTHS[m - 1].upper(), "mono", 10, left + i * step, h - 14, C["muted"], tracking=1))
        last_month = m
    nx = left + (len(weeks) - 1) * step + bw / 2
    b.append(f'<path d="M {nx - 4:.1f} {ground + 10} l 4 -5 l 4 5 z" fill="{C["amber"]}"/>')
    b.append(T("now", "mono", 10, nx, ground + 23, C["amber"], anchor="middle", tracking=.8))
    b.append(T("harput", "mono", 10, 124, h - 14, C["muted"], anchor="middle", tracking=1))
    b.append("</g>")
    b.append(f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="18" fill="none" stroke="{C["line"]}"/>')

    css = (
        ".tw{animation:tw 4s ease-in-out infinite}@keyframes tw{50%{opacity:.1}}"
        ".fl{animation:fl 9s steps(1) infinite}@keyframes fl{40%{opacity:0}60%{opacity:.85}}"
        ".beacon{animation:led 1.4s steps(1) infinite}@keyframes led{50%{opacity:.1}}"
        ".sh{animation:sh 6s ease-in-out infinite alternate}@keyframes sh{to{transform:translateX(40px);opacity:.3}}"
    )
    title = f"Elazığ skyline: {data['total']} contributions in the last year, one building per week"
    return doc(w, h, title, "".join(b), css)


def castle(x, base):
    fill, dark = "#151C27", "#0A0E14"
    parts = []

    def merlons(x0, x1, top):
        k = x0
        while k + 4 <= x1:
            parts.append(f'<rect x="{k:.0f}" y="{top - 6}" width="5" height="6" fill="{fill}"/>')
            k += 9

    parts.append(f'<rect x="{x}" y="{base}" width="128" height="46" fill="{fill}"/>')
    merlons(x + 4, x + 124, base)
    parts.append(f'<rect x="{x + 128}" y="{base + 16}" width="40" height="30" fill="{fill}"/>')
    merlons(x + 130, x + 166, base + 16)
    for tx, tw, th in ((x - 8, 22, 62), (x + 50, 30, 80), (x + 116, 20, 58)):
        top = base + 46 - th
        parts.append(f'<rect x="{tx}" y="{top}" width="{tw}" height="{th}" fill="{fill}"/>')
        merlons(tx + 1, tx + tw, top)
        parts.append(f'<rect x="{tx + tw / 2 - 1.5:.1f}" y="{top + 12}" width="3" height="6" fill="{C["amber"]}" fill-opacity=".85"/>')
    parts.append(f'<path d="M {x + 84} {base + 46} v -16 a 7 7 0 0 1 14 0 v 16 z" fill="{dark}"/>')
    for wx in (x + 20, x + 108, x + 146):
        parts.append(f'<rect x="{wx}" y="{base + 18}" width="3" height="5" fill="{C["amber"]}" fill-opacity=".6"/>')
    return "".join(parts)


# ---------------------------------------------------------------- stats

def build_stats(data):
    w, h = 1000, 216
    b = [dot_grid(w, h, "g2")]
    col_w = (w - 80) / 4
    metrics = [
        ("CONTRIBUTIONS", f"{data['total']:,}", "last 12 months"),
        ("CURRENT STREAK", f"{data['streak']}", "days in a row"),
        ("LONGEST STREAK", f"{data['longest']}", data["longest_range"]),
        ("BUSIEST DAY", data["busiest_day"], f"{data['repos']} public repos"),
    ]
    for i, (label, value, sub) in enumerate(metrics):
        x = 40 + i * col_w + (24 if i else 0)
        if i:
            b.append(f'<line x1="{40 + i * col_w:.1f}" y1="34" x2="{40 + i * col_w:.1f}" y2="128" stroke="{C["line"]}"/>')
        b.append(T(label, "mono", 11, x, 48, C["muted"], tracking=1.6))
        size = 42
        while W(value, "display", size, -1) > col_w - 40:
            size -= 2
        b.append(T(value, "display", size, x - 2, 98, C["amber"] if i == 1 else C["text"], tracking=-1))
        b.append(T(sub, "mono", 12, x, 123, C["soft"]))

    langs = data["languages"]
    total = sum(v for _, v, _ in langs) or 1
    x, bar_w, y = 40, w - 80, 152
    b.append(f'<clipPath id="lb"><rect x="{x}" y="{y}" width="{bar_w}" height="8" rx="4"/></clipPath><g clip-path="url(#lb)">')
    for name, size, color in langs:
        seg = bar_w * size / total
        b.append(f'<rect x="{x:.1f}" y="{y}" width="{seg + .5:.1f}" height="8" fill="{color}"/>')
        x += seg
    b.append("</g>")
    lx = 40
    for name, size, color in langs[:7]:
        label = f"{name} {size / total * 100:.0f}%"
        b.append(f'<circle cx="{lx + 4}" cy="186" r="4" fill="{color}"/>')
        b.append(T(label, "mono", 12, lx + 14, 190.5, C["soft"]))
        lx += W(label, "mono", 12) + 30
    b.append(f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="18" fill="none" stroke="{C["line"]}"/>')
    return doc(w, h, f"GitHub stats: {data['total']} contributions, {data['streak']} day streak", "".join(b))


# ---------------------------------------------------------------- projects

def build_project(i, p):
    w, h = 490, 232
    tone = TONES[p["tone"]]
    b = [f'<rect width="{w}" height="{h}" rx="16" fill="{C["ink"]}"/>']
    b.append(T(f"{i:02d}", "display", 150, w - 22, h + 26, C["panel2"], anchor="end", tracking=-6))
    b.append(f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="16" fill="none" stroke="{C["line"]}"/>')
    b.append(f'<rect x="0" y="28" width="3" height="40" rx="1.5" fill="{tone}"/>')
    b.append(T(f"{i:02d}", "monob", 12, 28, 44, tone, tracking=1))
    b.append(T(p["kind"], "mono", 11, 58, 44, C["muted"], tracking=1.4))
    status = p["status"].upper()
    sw = W(status, "mono", 10, 1.2) + 34
    b.append(f'<rect x="{w - 28 - sw:.1f}" y="27" width="{sw:.1f}" height="24" rx="12" fill="none" stroke="{tone}" stroke-opacity=".5"/>')
    pulse = ' class="pulse"' if p["status"] == "live" else ""
    b.append(f'<circle{pulse} cx="{w - 28 - sw + 14:.1f}" cy="39" r="3.5" fill="{tone}"/>')
    b.append(T(status, "mono", 10, w - 28 - sw + 24, 42.5, tone, tracking=1.2))
    b.append(T(p["title"], "display", 28, 27, 94, C["text"], tracking=-0.6))
    for k, line in enumerate(wrap(p["desc"], "text", 14.5, w - 60)[:3]):
        b.append(T(line, "text", 14.5, 28, 124 + k * 22, C["soft"]))
    cx = 28
    for s in p["stack"]:
        if cx + W(s, "mono", 10.5) + 22 > w - 28:
            break
        part, cw = chip(s, cx, 186, size=10.5, h=22, pad=9, tracking=0.2, fill=C["panel"])
        b.append(part)
        cx += cw + 6
    css = ".pulse{animation:p 1.6s ease-in-out infinite}@keyframes p{50%{opacity:.25}}"
    return doc(w, h, f"{p['title']} — {p['desc']}", "".join(b), css)


# ---------------------------------------------------------------- toolbox

def build_toolbox():
    rows = CONFIG["toolbox"]
    w, row_h = 1000, 42
    h = 44 + len(rows) * row_h + 14
    b = [f'<rect width="{w}" height="{h}" rx="18" fill="{C["ink"]}"/>',
         f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="18" fill="none" stroke="{C["line"]}"/>']
    b.append(T("● daily driver", "mono", 11, w - 40, 30, C["muted"], anchor="end", tracking=.6))
    b.append(f'<circle cx="{w - 40 - W("● daily driver", "mono", 11, .6) + 3.8:.1f}" cy="26" r="3.6" fill="{C["amber"]}"/>')
    for r, row in enumerate(rows):
        y = 44 + r * row_h
        b.append(T(row["label"].upper(), "mono", 11, 40, y + 17, C["muted"], tracking=1.8))
        cx = 170
        for item in row["items"]:
            hot = item.startswith("*")
            label = item.lstrip("*")
            part, cw = chip(label, cx, y, face="semi", size=13, h=26, pad=12, tracking=0,
                            color=C["text"] if hot else C["soft"], fill=C["panel"],
                            dot=C["amber"] if hot else None)
            b.append(part)
            cx += cw + 8
        if r < len(rows) - 1:
            b.append(f'<line x1="40" y1="{y + row_h - 8}" x2="{w - 40}" y2="{y + row_h - 8}" stroke="{C["grid"]}"/>')
    return doc(w, h, "Toolbox: " + ", ".join(i.lstrip("*") for r in rows for i in r["items"]), "".join(b))


# ---------------------------------------------------------------- footer

def build_footer(now):
    w, h = 1000, 86
    pts, x = [], 40
    rnd = random.Random(now.toordinal())
    while x < w - 40:
        y = 30 + (rnd.choice((-1, 1)) * rnd.uniform(4, 14) if rnd.random() < .18 else 0)
        pts.append(f"{x:.0f},{y:.0f}")
        x += 14
    b = [f'<polyline points="{" ".join(pts)}" fill="none" stroke="{C["line"]}" stroke-width="1.5"/>',
         f'<polyline class="trace" points="{" ".join(pts)}" fill="none" stroke="{C["amber"]}" stroke-width="1.5"/>']
    text = f"hand-drawn svg  ·  no templates  ·  rebuilt by a bot every night  ·  last build {now:%Y-%m-%d %H:%M} UTC"
    b.append(T(text, "mono", 12, w / 2, 72, C["muted"], anchor="middle", tracking=.3))
    css = ".trace{stroke-dasharray:60 2000;animation:tr 7s linear infinite}@keyframes tr{from{stroke-dashoffset:60}to{stroke-dashoffset:-1000}}"
    return doc(w, h, "footer", "".join(b), css)


# ---------------------------------------------------------------- data

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection { contributionCalendar { totalContributions
      weeks { contributionDays { date contributionCount weekday } } } }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      totalCount
      nodes { languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } } }
    }
  }
}"""


def gh(url, token, payload=None):
    req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload else None)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", f"{USER}-profile-builder")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def live_data(token):
    res = gh("https://api.github.com/graphql", token, {"query": QUERY, "variables": {"login": USER}})
    if "errors" in res:
        raise RuntimeError(res["errors"])
    u = res["data"]["user"]
    cal = u["contributionsCollection"]["contributionCalendar"]
    weeks = [[{"date": d["date"], "count": d["contributionCount"], "weekday": d["weekday"]}
              for d in wk["contributionDays"]] for wk in cal["weeks"]]
    langs = {}
    for repo in u["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            n = e["node"]
            size, color = langs.get(n["name"], (0, n["color"]))
            langs[n["name"]] = (size + e["size"], n["color"] or "#8B949E")
    events = gh(f"https://api.github.com/users/{USER}/events/public?per_page=60", token)
    return shape(weeks, cal["totalContributions"], u["repositories"]["totalCount"], langs, events)


def sample_data(today):
    rnd = random.Random(23)
    start = today - dt.timedelta(days=today.weekday() + 1 + 52 * 7)
    weeks, day = [], start
    while day <= today:
        wk = []
        for _ in range(7):
            if day > today:
                break
            busy = 1 + 0.9 * (day.month in (3, 4, 7, 8, 10))
            n = 0 if rnd.random() < .45 else int(rnd.expovariate(1 / (3 * busy)))
            wk.append({"date": day.isoformat(), "count": n, "weekday": (day.weekday() + 1) % 7})
            day += dt.timedelta(days=1)
        weeks.append(wk)
    for d in weeks[-1][-6:]:
        d["count"] = max(d["count"], 2)
    total = sum(d["count"] for wk in weeks for d in wk)
    langs = {"PHP": (410000, "#4F5D95"), "Blade": (220000, "#f7523f"), "C#": (300000, "#178600"),
             "JavaScript": (180000, "#f1e05a"), "TypeScript": (120000, "#3178c6"), "CSS": (60000, "#663399"),
             "HTML": (50000, "#e34c26"), "Java": (8000, "#b07219")}
    events = [
        {"type": "PushEvent", "repo": {"name": f"{USER}/workout-api"}, "created_at": "2026-10-19T18:02:00Z", "payload": {"size": 3}},
        {"type": "CreateEvent", "repo": {"name": f"{USER}/library-app"}, "created_at": "2026-10-12T10:00:00Z", "payload": {"ref_type": "repository"}},
        {"type": "PullRequestEvent", "repo": {"name": "FatLat/vito"}, "created_at": "2026-10-07T09:00:00Z",
         "payload": {"action": "opened", "number": 4, "pull_request": {"html_url": "https://github.com/FatLat/vito/pulls"}}},
    ]
    return shape(weeks, total, 24, langs, events)


def shape(weeks, total, repo_count, langs, events):
    days = [d for wk in weeks for d in wk]
    today = dt.date.fromisoformat(days[-1]["date"])
    streak, i = 0, len(days) - 1
    if days[i]["count"] == 0:
        i -= 1
    while i >= 0 and days[i]["count"] > 0:
        streak += 1
        i -= 1
    longest, run, best_end = 0, 0, None
    for k, d in enumerate(days):
        run = run + 1 if d["count"] else 0
        if run > longest:
            longest, best_end = run, k
    if longest:
        a = dt.date.fromisoformat(days[best_end - longest + 1]["date"])
        z = dt.date.fromisoformat(days[best_end]["date"])
        rng = f"{a:%b %d} – {z:%b %d}" if longest > 1 else f"{a:%b %d}"
    else:
        rng = "not yet"
    by_day = [0] * 7
    for d in days:
        by_day[d["weekday"]] += d["count"]
    names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    ranked = sorted(langs.items(), key=lambda kv: -kv[1][0])
    return {
        "weeks": weeks, "total": total, "streak": streak, "longest": longest, "longest_range": rng,
        "busiest_day": names[by_day.index(max(by_day))] if any(by_day) else "—",
        "repos": repo_count, "languages": [(n, s, c) for n, (s, c) in ranked], "events": events, "today": today,
    }


# ---------------------------------------------------------------- readme activity

def describe(e):
    repo = e["repo"]["name"]
    link = f"[{repo}](https://github.com/{repo})"
    p, t = e.get("payload", {}), e["type"]
    if t == "PushEvent":
        n = p.get("size") or p.get("distinct_size")
        if not n:
            return f"pushed to {link}"
        return f"pushed {n} commit{'s' if n != 1 else ''} to {link}"
    if t == "CreateEvent" and p.get("ref_type") == "repository":
        return f"created {link}"
    if t == "CreateEvent" and p.get("ref_type") == "tag":
        return f"tagged `{p.get('ref')}` in {link}"
    if t == "PullRequestEvent":
        pr = p.get("pull_request", {})
        verb = "merged" if p.get("action") == "closed" and pr.get("merged") else p.get("action", "updated")
        number = p.get("number") or pr.get("number")
        url = pr.get("html_url") or f"https://github.com/{repo}/pull/{number}"
        return f"{verb} [PR #{number}]({url}) in {link}"
    if t == "ReleaseEvent":
        return f"released `{p.get('release', {}).get('tag_name', '')}` of {link}"
    if t == "ForkEvent":
        return f"forked {link}"
    if t == "WatchEvent":
        return f"starred {link}"
    if t == "PublicEvent":
        return f"open-sourced {link}"
    return None


def update_readme(data):
    path = next((f for f in ROOT.iterdir() if f.name.lower() == "readme.md"), ROOT / "README.md")
    text = path.read_text(encoding="utf-8")
    lines, seen = [], set()
    seen_prs = set()
    for e in data["events"]:
        if e["repo"]["name"].lower() == f"{USER}/{USER}".lower():
            continue
        if e["type"] == "PullRequestEvent":
            pr_key = (e["repo"]["name"], e.get("payload", {}).get("number"))
            if pr_key in seen_prs:
                continue
            seen_prs.add(pr_key)
        line = describe(e)
        if not line or line in seen:
            continue
        seen.add(line)
        day = dt.datetime.fromisoformat(e["created_at"].replace("Z", "+00:00"))
        lines.append(f"- `{day:%b %d}` &nbsp;{line}")
        if len(lines) == 6:
            break
    if not lines:
        lines = ["- quiet week on public repos — probably soldering something."]
    block = "<!-- activity:start -->\n" + "\n".join(lines) + "\n<!-- activity:end -->"
    new = re.sub(r"<!-- activity:start -->.*?<!-- activity:end -->", block, text, flags=re.S)
    path.write_text(new, encoding="utf-8")


# ---------------------------------------------------------------- main

def main():
    now = dt.datetime.now(dt.timezone.utc)
    if "--sample" in sys.argv:
        data = sample_data(now.date())
    else:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            sys.exit("GH_TOKEN is not set (use --sample for an offline preview)")
        data = live_data(token)

    out = {
        "header.svg": build_header(now),
        "skyline.svg": build_skyline(data),
        "stats.svg": build_stats(data),
        "toolbox.svg": build_toolbox(),
        "footer.svg": build_footer(now),
    }
    for i, p in enumerate(CONFIG["projects"], 1):
        out[f"projects/{i:02d}.svg"] = build_project(i, p)
    for name, svg in out.items():
        target = ASSETS / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(svg, encoding="utf-8")
        print(f"{name:<18} {len(svg) / 1024:6.1f} KB")
    update_readme(data)


if __name__ == "__main__":
    main()
