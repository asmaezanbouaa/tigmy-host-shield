#!/usr/bin/env python3
"""Illustrated getting-started guide (PDF, French) for a new host.

Usage:
  python scripts/make_host_guide.py --out guide-hote.pdf          # standard guide, for any host
  python scripts/make_host_guide.py --out guide-younes.pdf --name Younes \
      --username younes_dhirech --slug younes-dhirech             # personalised copy

The standard guide has blank lines where the host writes their identifier and link.
The password is never printed in the guide: it is given to the host separately.
Bank details are not printed either (the host sees them inside the platform).
"""

import argparse
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

from app.config import get_settings
from app.services.packs import PACKS, TOPUP, TRIAL
from app.services.qrcode_gen import make_qr_png

W, H = A4
M = 42

IVORY, SAND = "#fbf7f1", "#f5ecdf"
CLAY, CLAY2, CLAY_D = "#b8532d", "#d0693c", "#7a3319"
EM, EM2, EM_D = "#0f5a48", "#14705a", "#0a4034"
GOLD, GOLD2 = "#e9b949", "#f6d88c"
INK, INK2, MUTED, LINE = "#2b1f18", "#5c4a3f", "#8a776a", "#e6d6c0"
BLUE, WHITE = "#2d47c2", "#ffffff"
SERIF, SERIF_B = "Times-Roman", "Times-Bold"
SANS, SANS_B = "Helvetica", "Helvetica-Bold"
LOGO = ROOT / "app" / "static" / "img" / "logo-192.png"


# ------------------------------------------------------------------ drawing helpers
def col(c, fill=None, stroke=None, lw=None):
    if fill:
        c.setFillColor(fill)
    if stroke:
        c.setStrokeColor(stroke)
    if lw is not None:
        c.setLineWidth(lw)


def rrect(c, x, y, w, h, r=8, fill=None, stroke=None, lw=1):
    col(c, fill, stroke, lw)
    c.roundRect(x, y, w, h, r, fill=1 if fill else 0, stroke=1 if stroke else 0)


def txt(c, s, x, y, font=SANS, size=10, color=INK, align="l"):
    c.setFont(font, size)
    c.setFillColor(color)
    {"l": c.drawString, "c": c.drawCentredString, "r": c.drawRightString}[align](x, y, s)


def para(c, s, x, y, w, font=SANS, size=10, color=INK2, leading=None):
    """Draw wrapped text from (x, y) downwards; returns the y under the last line."""
    leading = leading or size * 1.42
    c.setFont(font, size)
    c.setFillColor(color)
    for line in simpleSplit(s, font, size, w):
        c.drawString(x, y, line)
        y -= leading
    return y


def diamond(c, cx, cy, r, fill):
    col(c, fill)
    p = c.beginPath()
    p.moveTo(cx, cy + r)
    p.lineTo(cx + r, cy)
    p.lineTo(cx, cy - r)
    p.lineTo(cx - r, cy)
    p.close()
    c.drawPath(p, fill=1, stroke=0)


def zstrip(c, y, h=13, x0=0, x1=W):
    """Multicolour zellij border band."""
    col(c, IVORY)
    c.rect(x0, y, x1 - x0, h, fill=1, stroke=0)
    col(c, BLUE)
    c.rect(x0, y, x1 - x0, 1.6, fill=1, stroke=0)
    c.rect(x0, y + h - 1.6, x1 - x0, 1.6, fill=1, stroke=0)
    step = h * 2
    x = x0 + h
    cy = y + h / 2
    while x < x1 + h:
        diamond(c, x - h / 2, cy, h / 2 - 1.2, EM)
        diamond(c, x - h / 2, cy, h / 5, GOLD)
        diamond(c, x + h / 2, cy, h / 2 - 1.2, CLAY2)
        diamond(c, x, cy, h / 6, BLUE)
        x += step


def star_pattern(c, x, y, w, h, color, alpha=0.1, cell=46):
    """Light eight-point-star tiling clipped to a rectangle."""
    c.saveState()
    p = c.beginPath()
    p.rect(x, y, w, h)
    c.clipPath(p, stroke=0, fill=0)
    c.setStrokeColor(color)
    c.setLineWidth(0.7)
    c.setStrokeAlpha(alpha)
    r = cell * 0.35
    ny, nx = int(h // cell) + 2, int(w // cell) + 2
    for i in range(nx):
        for j in range(ny):
            cx, cy = x + i * cell, y + j * cell
            for ang in (0, 45):
                c.saveState()
                c.translate(cx, cy)
                c.rotate(ang)
                c.rect(-r, -r, 2 * r, 2 * r, fill=0, stroke=1)
                c.restoreState()
            c.circle(cx, cy, 2, fill=0, stroke=1)
    c.restoreState()


def shadow_card(c, x, y, w, h, r=12, fill=WHITE, stroke=LINE):
    col(c, "#e9dcc9")
    c.setFillAlpha(0.55)
    c.roundRect(x + 1.5, y - 2.5, w, h, r, fill=1, stroke=0)
    c.setFillAlpha(1)
    rrect(c, x, y, w, h, r, fill, stroke, 0.8)


def check(c, cx, cy, s, color=WHITE, lw=2):
    c.setStrokeColor(color)
    c.setLineWidth(lw)
    c.setLineCap(1)
    c.setLineJoin(1)
    p = c.beginPath()
    p.moveTo(cx - s * 0.5, cy)
    p.lineTo(cx - s * 0.12, cy - s * 0.38)
    p.lineTo(cx + s * 0.55, cy + s * 0.42)
    c.drawPath(p, stroke=1, fill=0)


def disc(c, cx, cy, r, fill):
    col(c, fill)
    c.circle(cx, cy, r, fill=1, stroke=0)


def badge(c, cx, cy, n, r=11, fill=CLAY):
    disc(c, cx, cy, r, fill)
    txt(c, str(n), cx, cy - r * 0.36, SANS_B, r * 1.05, WHITE, "c")


def arrow(c, x1, y1, x2, y2, color=CLAY2, lw=2):
    import math

    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(lw)
    c.setLineCap(1)
    c.line(x1, y1, x2, y2)
    a = math.atan2(y2 - y1, x2 - x1)
    L = 7
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(x2 - L * math.cos(a - 0.45), y2 - L * math.sin(a - 0.45))
    p.lineTo(x2 - L * math.cos(a + 0.45), y2 - L * math.sin(a + 0.45))
    p.close()
    c.drawPath(p, fill=1, stroke=0)


def chip(c, x, y, label, fill, color, font=SANS_B, size=7.5, padx=7, h=14):
    w = c.stringWidth(label, font, size) + padx * 2
    rrect(c, x, y, w, h, h / 2, fill)
    txt(c, label, x + padx, y + h / 2 - size * 0.33, font, size, color)
    return w


def button(c, x, y, w, h, label, fill=CLAY, color=WHITE, size=8.5, stroke=None):
    rrect(c, x, y, w, h, h / 2, fill, stroke, 1)
    txt(c, label, x + w / 2, y + h / 2 - size * 0.33, SANS_B, size, color, "c")


def field(c, x, y, w, label, value, h=24):
    txt(c, label, x, y + h + 4, SANS_B, 7.5, INK2)
    rrect(c, x, y, w, h, 6, WHITE, LINE, 1)
    txt(c, value, x + 8, y + h / 2 - 3, SANS, 8.5, INK)


# ---- icons (drawn at centre cx, cy, in a ~20pt box)
def icon_qr(c, cx, cy, s=18, color=WHITE):
    col(c, color)
    u = s / 7
    for gx, gy in ((0, 0), (4, 0), (0, 4)):
        c.rect(cx - s / 2 + gx * u, cy + s / 2 - (gy + 3) * u, 3 * u, 3 * u, fill=0, stroke=1)
        c.rect(cx - s / 2 + (gx + 1) * u, cy + s / 2 - (gy + 2) * u, u, u, fill=1, stroke=0)
    c.rect(cx + s / 2 - 2 * u, cy - s / 2, 2 * u, 2 * u, fill=1, stroke=0)
    c.rect(cx, cy - s / 2 + 2.5 * u, u, u, fill=1, stroke=0)


def icon_phone(c, cx, cy, s=18, color=WHITE):
    c.setStrokeColor(color)
    c.setLineWidth(1.6)
    c.roundRect(cx - s * 0.3, cy - s / 2, s * 0.6, s, 3, fill=0, stroke=1)
    col(c, color)
    c.circle(cx, cy - s * 0.38, 1.1, fill=1, stroke=0)


def icon_shield(c, cx, cy, s=18, color=WHITE):
    c.setStrokeColor(color)
    c.setLineWidth(1.6)
    p = c.beginPath()
    p.moveTo(cx, cy + s / 2)
    p.lineTo(cx + s * 0.42, cy + s * 0.34)
    p.lineTo(cx + s * 0.42, cy - s * 0.05)
    p.curveTo(cx + s * 0.42, cy - s * 0.3, cx + s * 0.1, cy - s * 0.45, cx, cy - s / 2)
    p.curveTo(cx - s * 0.1, cy - s * 0.45, cx - s * 0.42, cy - s * 0.3, cx - s * 0.42, cy - s * 0.05)
    p.lineTo(cx - s * 0.42, cy + s * 0.34)
    p.close()
    c.drawPath(p, stroke=1, fill=0)
    check(c, cx, cy, s * 0.36, color, 1.6)


def icon_doc(c, cx, cy, s=18, color=WHITE):
    c.setStrokeColor(color)
    c.setLineWidth(1.6)
    c.roundRect(cx - s * 0.33, cy - s / 2, s * 0.66, s, 2.5, fill=0, stroke=1)
    for k in (0.12, -0.08, -0.28):
        c.line(cx - s * 0.18, cy + s * k, cx + s * 0.18, cy + s * k)


def icon_house(c, cx, cy, s=18, color=WHITE):
    c.setStrokeColor(color)
    c.setLineWidth(1.6)
    c.setLineJoin(1)
    p = c.beginPath()
    p.moveTo(cx - s * 0.5, cy)
    p.lineTo(cx, cy + s * 0.48)
    p.lineTo(cx + s * 0.5, cy)
    c.drawPath(p, stroke=1, fill=0)
    c.rect(cx - s * 0.34, cy - s * 0.46, s * 0.68, s * 0.46, fill=0, stroke=1)
    c.rect(cx - s * 0.1, cy - s * 0.46, s * 0.2, s * 0.3, fill=0, stroke=1)


def icon_chat(c, cx, cy, s=18, color=WHITE):
    c.setStrokeColor(color)
    c.setLineWidth(1.6)
    c.circle(cx, cy + s * 0.04, s * 0.42, fill=0, stroke=1)
    for k in (-0.17, 0, 0.17):
        col(c, color)
        c.circle(cx + s * k, cy + s * 0.04, 1.1, fill=1, stroke=0)


def icon_user(c, cx, cy, s=18, color=WHITE):
    c.setStrokeColor(color)
    c.setLineWidth(1.6)
    c.circle(cx, cy + s * 0.2, s * 0.2, fill=0, stroke=1)
    p = c.beginPath()
    p.arc(cx - s * 0.4, cy - s * 0.55, cx + s * 0.4, cy + s * 0.05, 0, 180)
    c.drawPath(p, stroke=1, fill=0)


def icon_clock(c, cx, cy, s=18, color=WHITE):
    c.setStrokeColor(color)
    c.setLineWidth(1.6)
    c.circle(cx, cy, s * 0.46, fill=0, stroke=1)
    c.line(cx, cy, cx, cy + s * 0.28)
    c.line(cx, cy, cx + s * 0.22, cy - s * 0.1)


def tile(c, cx, cy, icon, fill=EM, r=20):
    rrect(c, cx - r, cy - r, 2 * r, 2 * r, 12, fill)
    icon(c, cx, cy, r * 1.0)


# ---- mockups
def phone(c, x, y, w, h):
    """Phone body; returns the screen rectangle (sx, sy, sw, sh)."""
    shadow_card(c, x, y, w, h, 16, "#2b1f18", "#2b1f18")
    pad = 4
    rrect(c, x + pad, y + pad, w - 2 * pad, h - 2 * pad, 13, IVORY)
    rrect(c, x + w / 2 - 14, y + h - pad - 5, 28, 4, 2, "#2b1f18")
    return x + pad, y + pad, w - 2 * pad, h - 2 * pad - 8


def browser(c, x, y, w, h, url):
    shadow_card(c, x, y, w, h, 10, WHITE, LINE)
    rrect(c, x, y + h - 22, w, 22, 10, SAND)
    c.setFillColor(SAND)
    c.rect(x, y + h - 22, w, 10, fill=1, stroke=0)
    for i, colr in enumerate(("#e5806a", GOLD, "#6fbf9f")):
        disc(c, x + 12 + i * 11, y + h - 11, 3.2, colr)
    rrect(c, x + 48, y + h - 18, w - 60, 14, 7, WHITE, LINE, 0.6)
    txt(c, url, x + 56, y + h - 13.5, SANS, 6.8, MUTED)
    return x, y, w, h - 22


def callout(c, x, y, n):
    badge(c, x, y, n, 9, CLAY)


# ------------------------------------------------------------------ page chrome
def page_bg(c):
    col(c, IVORY)
    c.rect(0, 0, W, H, fill=1, stroke=0)


def footer(c, n, total, brand="Tigmi Host Shield"):
    c.setStrokeColor(LINE)
    c.setLineWidth(0.8)
    c.line(M, 36, W - M, 36)
    txt(c, f"{brand}  ·  Guide de démarrage", M, 22, SANS, 8, MUTED)
    txt(c, f"{n} / {total}", W - M, 22, SANS, 8, MUTED, "r")


def step_header(c, n, title, subtitle):
    star_pattern(c, 0, H - 118, W, 118, EM, 0.1)
    zstrip(c, H - 118, 12)
    badge(c, M + 18, H - 62, n, 18, CLAY) if isinstance(n, int) else tile(c, M + 18, H - 62, n, CLAY, 18)
    txt(c, title, M + 48, H - 66, SERIF_B, 25, INK)
    txt(c, subtitle, M + 48, H - 86, SANS, 10.5, INK2)


def tip_box(c, x, y, w, title, body, color=GOLD, bg="#fdf4e3", ink="#6b4a0b"):
    lines = simpleSplit(body, SANS, 9.2, w - 52)
    h = 24 + len(lines) * 13 + 6
    rrect(c, x, y - h, w, h, 10, bg)
    rrect(c, x, y - h, 5, h, 2.5, color)
    txt(c, title, x + 18, y - 17, SANS_B, 9.5, ink)
    yy = y - 31
    for ln in lines:
        txt(c, ln, x + 18, yy, SANS, 9.2, ink)
        yy -= 13
    return y - h - 10


def numbered(c, x, y, w, items, gap=9):
    """Numbered steps: list of (title, body). Returns y under the list."""
    for i, (t, b) in enumerate(items, 1):
        badge(c, x + 11, y - 4, i, 10.5, EM)
        txt(c, t, x + 30, y - 7, SANS_B, 10.5, INK)
        y = para(c, b, x + 30, y - 21, w - 30, SANS, 9.4, INK2, 12.8)
        y -= gap
    return y


# ------------------------------------------------------------------ pages
def page_cover(c, a):
    page_bg(c)
    star_pattern(c, 0, 0, W, H, EM, 0.07, 52)
    # horseshoe arch panel
    ax, ay, aw, ah = W - 290, 150, 250, 520
    arch = c.beginPath()
    r = aw / 2
    arch.moveTo(ax, ay)
    arch.lineTo(ax + aw, ay)
    arch.lineTo(ax + aw, ay + ah - r)
    arch.arcTo(ax, ay + ah - 2 * r, ax + aw, ay + ah, 0, 180)
    arch.close()
    col(c, GOLD)
    c.saveState()
    c.translate(0, 0)
    c.setLineWidth(0)
    c.setFillColor(GOLD)
    c.drawPath(arch, fill=1, stroke=0)
    c.restoreState()
    arch2 = c.beginPath()
    i = 7
    arch2.moveTo(ax + i, ay + i)
    arch2.lineTo(ax + aw - i, ay + i)
    arch2.lineTo(ax + aw - i, ay + ah - r)
    arch2.arcTo(ax + i, ay + ah - 2 * r + i, ax + aw - i, ay + ah - i, 0, 180)
    arch2.close()
    c.setFillColor(EM2)
    c.drawPath(arch2, fill=1, stroke=0)
    c.saveState()
    c.clipPath(arch2, stroke=0, fill=0)
    star_pattern(c, ax, ay, aw, ah, GOLD, 0.35, 40)
    c.restoreState()
    # phone with scan in the arch
    px, py, pw, ph = ax + 45, ay + 70, 160, 300
    sx, sy, sw, sh = phone(c, px, py, pw, ph)
    txt(c, "Tigmi Host Shield", sx + 12, sy + sh - 14, SERIF_B, 9.5, INK)
    rrect(c, sx + 12, sy + sh - 86, sw - 24, 58, 7, "#f6e3b4", "#e5c987")
    rrect(c, sx + 20, sy + sh - 80, 20, 26, 3, "#b9a273")
    for k, ww in enumerate((52, 40, 30)):
        rrect(c, sx + 48, sy + sh - 42 - k * 9, ww, 4, 2, "#b99a55")
    col(c, "#4be3a6")
    c.setFillAlpha(0.45)
    c.rect(sx + 12, sy + sh - 62, sw - 24, 12, fill=1, stroke=0)
    c.setFillAlpha(1)
    rrect(c, sx + 12, sy + sh - 112, sw - 24, 18, 6, "#e4f3ee")
    txt(c, "Pièce vérifiée", sx + 18, sy + sh - 105, SANS_B, 7.5, EM)
    check(c, sx + sw - 24, sy + sh - 102, 7, EM, 1.6)
    field(c, sx + 12, sy + sh - 160, sw - 24, "Nom", "Sara BENNANI", 20)
    field(c, sx + 12, sy + sh - 202, sw - 24, "N° de pièce", "AB123456", 20)
    button(c, sx + 12, sy + 14, sw - 24, 22, "Envoyer ma fiche", CLAY)
    # floating chips on the arch
    shadow_card(c, ax - 36, ay + 360, 108, 36, 10)
    tile(c, ax - 18, ay + 378, icon_shield, EM, 11)
    txt(c, "Validée par l'IA", ax - 3, ay + 375, SANS_B, 7.8, INK)
    shadow_card(c, ax + aw - 74, ay + 40, 112, 36, 10)
    tile(c, ax + aw - 56, ay + 58, icon_doc, CLAY, 11)
    txt(c, "Contrat en PDF", ax + aw - 41, ay + 55, SANS_B, 7.8, INK)

    zstrip(c, H - 40, 16)
    zstrip(c, 24, 16)
    # texts
    c.drawImage(str(LOGO), M, H - 120, 46, 46, mask="auto")
    txt(c, "Tigmi Host Shield", M + 58, H - 102, SERIF_B, 17, INK)
    txt(c, "GUIDE DE DÉMARRAGE", M, H - 200, SANS_B, 10, CLAY)
    txt(c, "Bienvenue," if a.name else "Bienvenue", M, H - 252, SERIF_B, 44, INK)
    txt(c, (a.name + " !") if a.name else "chez Tigmi !", M, H - 300, SERIF_B, 44, CLAY)
    para(c, "Tout ce qu'il faut pour enregistrer vos voyageurs, pas à pas, en quelques minutes. "
         "Aucune connaissance technique nécessaire.", M, H - 335, 232, SANS, 12, INK2, 17)
    rrect(c, M, H - 506, 238, 92, 14, EM)
    star_pattern(c, M, H - 506, 238, 92, GOLD, 0.3, 30)
    txt(c, "VOTRE PACK DE BIENVENUE", M + 18, H - 436, SANS_B, 8.5, GOLD2)
    txt(c, f"{TRIAL['fiches']} fiches gratuites", M + 18, H - 466, SERIF_B, 23, WHITE)
    txt(c, f"pendant {TRIAL['days']} jours · jusqu'à 9 logements", M + 18, H - 488, SANS, 9.2, "#cfe9e0")
    txt(c, "Mon identifiant" if not a.username else "Votre identifiant", M, H - 550, SANS_B, 8.5, MUTED)
    txt(c, "Mon lien voyageurs" if not a.link else "Votre lien voyageurs", M, H - 605, SANS_B, 8.5, MUTED)
    if a.username:
        txt(c, a.username, M, H - 570, SANS_B, 14, INK)
        txt(c, a.link.replace("https://", ""), M, H - 623, SANS_B, 9.2, EM)
    else:  # standard guide: lines to fill in by hand
        c.setStrokeColor(MUTED)
        c.setLineWidth(0.8)
        c.line(M, H - 572, M + 232, H - 572)
        c.line(M, H - 627, M + 232, H - 627)


def page_overview(c, a):
    page_bg(c)
    step_header(c, icon_house, "Le principe en une image", "Comment votre voyageur arrive jusqu'à son contrat signé")
    y0 = H - 230
    steps = [
        (icon_qr, EM, "Vous partagez\nvotre lien"),
        (icon_phone, CLAY, "Le voyageur remplit\nsur son téléphone"),
        (icon_shield, EM, "L'IA vérifie\nsa pièce d'identité"),
        (icon_user, CLAY, "Vous contrôlez\net confirmez"),
        (icon_doc, EM, "Vous téléchargez\nle contrat"),
    ]
    cw = (W - 2 * M) / 5
    for i, (ic, colr, label) in enumerate(steps):
        cx = M + cw * i + cw / 2
        shadow_card(c, cx - 36, y0 - 38, 72, 90, 14)
        tile(c, cx, y0 + 18, ic, colr, 21)
        badge(c, cx - 28, y0 + 44, i + 1, 8.5, GOLD)
        for k, ln in enumerate(label.split("\n")):
            txt(c, ln, cx, y0 - 14 - k * 10, SANS_B, 7.4, INK, "c")
        if i < 4:
            arrow(c, cx + 38, y0 + 8, cx + cw - 38, y0 + 8, CLAY2, 1.8)
    y = y0 - 80
    # needs box
    shadow_card(c, M, y - 128, (W - 2 * M) / 2 - 8, 128, 14)
    txt(c, "Ce dont vous avez besoin", M + 16, y - 22, SERIF_B, 14, INK)
    needs = ["Un téléphone ou un ordinateur", "Une connexion internet", "L'adresse de vos logements"]
    for i, n in enumerate(needs):
        disc(c, M + 24, y - 50 - i * 24, 8, EM)
        check(c, M + 24, y - 50 - i * 24, 7, WHITE, 1.5)
        txt(c, n, M + 40, y - 53 - i * 24, SANS, 9.6, INK2)
    bx = M + (W - 2 * M) / 2 + 8
    shadow_card(c, bx, y - 128, (W - 2 * M) / 2 - 8, 128, 14)
    txt(c, "Combien de temps ?", bx + 16, y - 22, SERIF_B, 14, INK)
    tile(c, bx + 40, y - 70, icon_clock, CLAY, 20)
    txt(c, "10 minutes", bx + 72, y - 62, SERIF_B, 20, CLAY)
    para(c, "pour tout installer, une seule fois. Ensuite, chaque voyageur ne vous prend que quelques secondes.",
         bx + 72, y - 78, (W - 2 * M) / 2 - 100, SANS, 8.8, INK2, 11.5)
    y -= 160
    txt(c, "Les mots à connaître", M, y, SERIF_B, 17, INK)
    y -= 14
    words = [
        ("Fiche", "Un voyageur enregistré. Chaque voyageur qui envoie sa fiche utilise 1 fiche de votre pack."),
        ("Pack", "Votre réserve de fiches. Le pack de bienvenue vous en offre 50 pendant 30 jours."),
        ("Lien et QR code", "Votre adresse personnelle. Tous les voyageurs qui l'ouvrent arrivent chez vous."),
        ("IA", "L'intelligence artificielle lit la pièce d'identité et la compare à ce que le voyageur a écrit."),
        ("Logement", "Un appartement, un riad ou une chambre. Le voyageur choisit lequel dans une liste."),
    ]
    for i, (k, v) in enumerate(words):
        yy = y - i * 54
        rrect(c, M, yy - 44, W - 2 * M, 46, 10, WHITE, LINE, 0.8)
        rrect(c, M, yy - 44, 6, 46, 3, [EM, CLAY, GOLD, BLUE, EM][i])
        txt(c, k, M + 20, yy - 21, SANS_B, 10.5, INK)
        para(c, v, M + 130, yy - 17, W - 2 * M - 146, SANS, 9, INK2, 12)


def page_login(c, a):
    page_bg(c)
    step_header(c, 1, "Connectez-vous", "Ouvrez votre espace hôte")
    # browser mock
    bx, by, bw, bh = M, H - 400, 255, 255
    ix, iy, iw, ih = browser(c, bx, by, bw, bh, "tigmihostshield.duckdns.org/admin/login")
    c.drawImage(str(LOGO), ix + iw / 2 - 18, iy + ih - 52, 36, 36, mask="auto")
    txt(c, "Connexion", ix + iw / 2, iy + ih - 72, SERIF_B, 15, INK, "c")
    field(c, ix + 24, iy + ih - 128, iw - 48, "Identifiant", a.username or "votre.identifiant")
    field(c, ix + 24, iy + ih - 180, iw - 48, "Mot de passe", "••••••••••")
    button(c, ix + 24, iy + 22, iw - 48, 26, "Se connecter", CLAY)
    callout(c, ix + iw - 10, iy + ih - 100, 2)
    callout(c, ix + iw - 10, iy + 35, 3)
    callout(c, bx + 30, by + bh - 11, 1)
    sx = M + 285
    y = numbered(c, sx, H - 156, W - sx - M, [
        ("Ouvrez le site", "Tapez  tigmihostshield.duckdns.org  puis touchez le bouton « Espace hôte » en haut à droite."),
        ("Entrez vos identifiants", (f"Identifiant : {a.username}. " if a.username else "Votre identifiant et votre mot de passe ")
                                  + ("Le mot de passe vous est remis séparément, en privé." if a.username else "vous sont remis séparément, en privé.")),
        ("Touchez « Se connecter »", "Vous arrivez sur votre tableau de bord."),
    ])
    y = tip_box(c, sx, y - 4, W - sx - M, "Astuce",
                "Ajoutez le site à l'écran d'accueil de votre téléphone pour l'ouvrir en un geste.")
    # change password
    yy = H - 440
    txt(c, "Premier réflexe : changez votre mot de passe", M, yy, SERIF_B, 16, INK)
    shadow_card(c, M, yy - 130, W - 2 * M, 110, 14)
    tile(c, M + 36, yy - 62, icon_user, EM, 20)
    items = [("Ouvrez « Mon profil »", "En bas du menu, touchez votre nom (ou la petite icône ronde en haut sur téléphone)."),
             ("Changez le mot de passe", "Remplissez l'ancien mot de passe, puis le nouveau, puis confirmez-le."),
             ("Touchez « Mettre à jour »", "Choisissez 10 caractères minimum, avec des lettres et des chiffres.")]
    for i, (t, b) in enumerate(items):
        xx = M + 78 + i * 150
        badge(c, xx + 8, yy - 44, i + 1, 9, CLAY)
        txt(c, t, xx + 22, yy - 47, SANS_B, 8.4, INK)
        para(c, b, xx, yy - 64, 136, SANS, 8.4, INK2, 11)
    # fix long titles
    tip_box(c, M, yy - 148, W - 2 * M, "Important",
            "Ne partagez votre mot de passe avec personne. Si vous l'oubliez, écrivez-nous sur WhatsApp : "
            "nous le réinitialisons.", CLAY, "#fdf1ea", CLAY_D)


def page_apartments(c, a):
    page_bg(c)
    step_header(c, 2, "Ajoutez vos logements", "Le voyageur choisira le sien dans une liste")
    # menu mock + form mock
    mx, my, mw, mh = M, H - 440, 150, 290
    shadow_card(c, mx, my, mw, mh, 12, EM, EM)
    star_pattern(c, mx, my, mw, mh, GOLD, 0.18, 30)
    items = ["Aperçu", "Fiches", "Calendrier", "Logements", "Lien et QR code", "Mon pack", "Archives"]
    for i, it in enumerate(items):
        yy = my + mh - 40 - i * 30
        if it == "Logements":
            rrect(c, mx + 8, yy - 9, mw - 16, 24, 8, "#2a8a74")
            rrect(c, mx + 8, yy - 9, mw - 16, 24, 8, None, GOLD, 1.2)
        txt(c, it, mx + 22, yy - 1, SANS_B if it == "Logements" else SANS, 9.2, WHITE)
    callout(c, mx + mw - 6, my + mh - 40 - 3 * 30 + 4, 1)
    fx, fy, fw, fh = M + 175, H - 440, W - 2 * M - 175, 290
    ix, iy, iw, ih = browser(c, fx, fy, fw, fh, "…/admin/apartments")
    txt(c, "Logements", ix + 16, iy + ih - 28, SERIF_B, 15, INK)
    field(c, ix + 16, iy + ih - 90, iw - 32, "Nom", "Appartement Agdal — Rabat")
    field(c, ix + 16, iy + ih - 142, iw - 32, "Adresse complète", "12 rue Oued Fès, Agdal, Rabat")
    button(c, ix + 16, iy + ih - 182, 90, 24, "Ajouter", CLAY)
    callout(c, ix + iw - 14, iy + ih - 78, 2)
    callout(c, ix + 124, iy + ih - 170, 3)
    # existing cards
    for k, nm in enumerate(("Riad Atlas — Suite 2", "Studio Médina — Fès")):
        yy = iy + 14 + k * 0
        rrect(c, ix + 16 + k * ((iw - 40) / 2 + 8), iy + 14, (iw - 40) / 2, 38, 8, SAND, LINE, 0.8)
        icon_house(c, ix + 32 + k * ((iw - 40) / 2 + 8), iy + 33, 12, EM)
        txt(c, nm, ix + 44 + k * ((iw - 40) / 2 + 8), iy + 30, SANS_B, 7.4, INK)
    y = H - 480
    y = numbered(c, M, y, W - 2 * M, [
        ("Touchez « Logements » dans le menu", "Sur téléphone : touchez « Plus » en bas de l'écran pour voir tout le menu."),
        ("Écrivez le nom et l'adresse", "Un nom que votre voyageur reconnaît tout de suite (ex. « Studio Médina »). L'adresse figure dans le contrat."),
        ("Touchez « Ajouter »", "Recommencez pour chaque logement. Vous pouvez en ajouter, modifier ou retirer à tout moment."),
    ])
    tip_box(c, M, y - 2, W - 2 * M, "Votre pack de bienvenue",
            "Il convient aux hôtes qui ont moins de 10 logements. Si vous en avez davantage, choisissez un autre pack dans « Mon pack ».",
            EM, "#e8f3ef", EM_D)


def page_link(c, a):
    page_bg(c)
    step_header(c, 3, "Partagez votre lien et votre QR code", "C'est ce que vous donnez à vos voyageurs")
    # share mock
    bx, by, bw, bh = M, H - 400, W - 2 * M, 240
    ix, iy, iw, ih = browser(c, bx, by, bw, bh, "…/admin/share")
    txt(c, "Lien et QR code", ix + 16, iy + ih - 28, SERIF_B, 15, INK)
    txt(c, "Votre lien voyageurs", ix + 16, iy + ih - 52, SANS_B, 8, INK2)
    rrect(c, ix + 16, iy + ih - 80, iw - 200, 24, 6, WHITE, LINE, 1)
    txt(c, (a.link or "https://tigmihostshield.duckdns.org/register/votre-nom").replace("https://", ""), ix + 24, iy + ih - 72, SANS, 7.4, EM)
    button(c, ix + iw - 176, iy + ih - 80, 62, 24, "Copier", CLAY, size=8)
    callout(c, ix + iw - 187, iy + ih - 58, 1)
    qr_png = make_qr_png(a.link or a.base, 6)
    shadow_card(c, ix + 16, iy + 16, 96, 96, 8)
    c.drawImage(ImageReader(io.BytesIO(qr_png)), ix + 20, iy + 20, 88, 88)
    button(c, ix + 122, iy + 58, 120, 24, "Télécharger le QR", WHITE, CLAY, 7.6, CLAY)
    callout(c, ix + 232, iy + 82, 2)
    rrect(c, ix + 122, iy + 16, 160, 32, 7, "#fdf4e3")
    txt(c, "« Générer un nouveau lien »", ix + 130, iy + 33, SANS_B, 7.4, "#6b4a0b")
    txt(c, "désactive l'ancien lien", ix + 130, iy + 22, SANS, 6.8, "#6b4a0b")
    # three ways
    yy = H - 440
    txt(c, "Trois façons de l'utiliser", M, yy, SERIF_B, 16, INK)
    ways = [
        (icon_chat, EM, "Par message", "Copiez le lien et envoyez-le par WhatsApp ou par la messagerie Airbnb avant l'arrivée."),
        (icon_qr, CLAY, "Par QR code", "Téléchargez le QR, imprimez-le et posez-le à l'entrée du logement ou à la réception."),
        (icon_phone, EM, "En direct", "Montrez le QR sur votre téléphone : le voyageur le scanne avec son appareil photo."),
    ]
    cw = (W - 2 * M - 24) / 3
    for i, (ic, colr, t, b) in enumerate(ways):
        x = M + i * (cw + 12)
        shadow_card(c, x, yy - 150, cw, 128, 14)
        tile(c, x + 34, yy - 56, ic, colr, 20)
        txt(c, t, x + 64, yy - 52, SANS_B, 10.5, INK)
        para(c, b, x + 16, yy - 88, cw - 30, SANS, 8.8, INK2, 11.8)
    tip_box(c, M, yy - 170, W - 2 * M, "Bon à savoir",
            "Ce lien est personnel : chaque fiche reçue arrive dans votre espace, jamais chez un autre hôte. "
            "Si vous pensez qu'il a été diffusé par erreur, générez-en un nouveau.")


def page_guest(c, a):
    page_bg(c)
    step_header(c, 4, "Ce que fait votre voyageur", "Cinq écrans, depuis son téléphone, sans application")
    pw, ph = 88, 190
    gap = (W - 2 * M - 5 * pw) / 4
    y = H - 355
    titles = ["Il ouvre le lien", "Il choisit son logement", "Il remplit sa fiche", "Il photographie sa pièce", "Il signe et envoie"]
    for i in range(5):
        x = M + i * (pw + gap)
        sx, sy, sw, sh = phone(c, x, y, pw, ph)
        if i == 0:
            c.drawImage(str(LOGO), sx + sw / 2 - 11, sy + sh - 36, 22, 22, mask="auto")
            txt(c, "Bienvenue", sx + sw / 2, sy + sh - 50, SERIF_B, 8, INK, "c")
            for k, lang in enumerate(("Français", "English", "العربية" if False else "Arabe")):
                rrect(c, sx + 8, sy + sh - 78 - k * 20, sw - 16, 15, 7, WHITE if k else EM, LINE, 0.8)
                txt(c, lang, sx + sw / 2, sy + sh - 73 - k * 20, SANS_B, 6.4, INK if k else WHITE, "c")
            button(c, sx + 8, sy + 10, sw - 16, 16, "Commencer", CLAY, size=6.6)
        elif i == 1:
            txt(c, "Votre logement", sx + 8, sy + sh - 18, SANS_B, 7, INK)
            for k, nm in enumerate(("Apt. Agdal", "Riad Atlas", "Studio Médina")):
                on = k == 0
                rrect(c, sx + 8, sy + sh - 48 - k * 28, sw - 16, 23, 6, "#e8f3ef" if on else WHITE, EM if on else LINE, 1)
                icon_house(c, sx + 20, sy + sh - 36.5 - k * 28, 9, EM)
                txt(c, nm, sx + 30, sy + sh - 39 - k * 28, SANS_B, 5.6, INK)
            field(c, sx + 8, sy + 38, sw - 16, "Arrivée", "20/10/2026", 16)
            button(c, sx + 8, sy + 8, sw - 16, 16, "Suivant", CLAY, size=6.6)
        elif i == 2:
            for k, (lb, v) in enumerate((("Nom", "BENNANI"), ("Prénom", "Sara"), ("Nationalité", "Française"), ("Naissance", "04/03/1992"))):
                field(c, sx + 8, sy + sh - 44 - k * 33, sw - 16, lb, v, 16)
            button(c, sx + 8, sy + 8, sw - 16, 16, "Suivant", CLAY, size=6.6)
        elif i == 3:
            txt(c, "Photo de la pièce", sx + 8, sy + sh - 18, SANS_B, 7, INK)
            rrect(c, sx + 8, sy + sh - 78, sw - 16, 50, 6, "#f6e3b4", "#e5c987")
            rrect(c, sx + 13, sy + sh - 72, 14, 18, 2, "#b9a273")
            for k, ww in enumerate((26, 20)):
                rrect(c, sx + 32, sy + sh - 60 - k * 7, ww, 3, 1.5, "#b99a55")
            rrect(c, sx + 8, sy + sh - 100, sw - 16, 16, 6, "#e4f3ee")
            txt(c, "Photo nette", sx + 14, sy + sh - 95, SANS_B, 6.2, EM)
            check(c, sx + sw - 18, sy + sh - 92, 5, EM, 1.4)
            button(c, sx + 8, sy + 8, sw - 16, 16, "Suivant", CLAY, size=6.6)
        else:
            txt(c, "Contrat", sx + 8, sy + sh - 18, SANS_B, 7, INK)
            for k in range(4):
                rrect(c, sx + 8, sy + sh - 34 - k * 8, sw - 16 - (k % 2) * 14, 3, 1.5, LINE)
            rrect(c, sx + 8, sy + 58, sw - 16, 42, 6, WHITE, LINE, 1)
            c.setStrokeColor(INK)
            c.setLineWidth(1.2)
            p = c.beginPath()
            p.moveTo(sx + 14, sy + 76)
            p.curveTo(sx + 22, sy + 96, sx + 28, sy + 62, sx + 38, sy + 82)
            p.curveTo(sx + 46, sy + 94, sx + 52, sy + 66, sx + 66, sy + 84)
            c.drawPath(p, stroke=1, fill=0)
            txt(c, "Signature", sx + 10, sy + 62, SANS, 5.5, MUTED)
            button(c, sx + 8, sy + 8, sw - 16, 16, "Envoyer", EM, size=6.6)
        badge(c, x + pw / 2, y - 18, i + 1, 9.5, CLAY)
        for k, ln in enumerate(simpleSplit(titles[i], SANS_B, 8.2, pw + gap - 6)):
            txt(c, ln, x + pw / 2, y - 38 - k * 10, SANS_B, 8.2, INK, "c")
        if i < 4:
            arrow(c, x + pw + 3, y + ph / 2, x + pw + gap - 3, y + ph / 2, CLAY2, 1.6)
    # what happens on the host side
    hy = y - 78
    shadow_card(c, M, hy - 100, W - 2 * M, 100, 14)
    txt(c, "Pendant ce temps, vous n'avez rien à faire", M + 18, hy - 26, SERIF_B, 14, INK)
    shadow_card(c, M + 18, hy - 88, 190, 44, 10, "#fdf4e3", "#f0d9a4")
    tile(c, M + 40, hy - 66, icon_user, CLAY, 12)
    txt(c, "Nouvelle fiche reçue", M + 60, hy - 61, SANS_B, 8.6, INK)
    txt(c, "BENNANI Sara · Apt. Agdal", M + 60, hy - 73, SANS, 7.6, INK2)
    arrow(c, M + 218, hy - 66, M + 246, hy - 66, CLAY2, 1.6)
    shadow_card(c, M + 256, hy - 88, 120, 44, 10, EM, EM)
    txt(c, "49 / 50", M + 270, hy - 68, SERIF_B, 17, WHITE)
    txt(c, "fiches restantes", M + 270, hy - 80, SANS, 6.8, "#cfe9e0")
    para(c, "La fiche arrive dans « Fiches » et votre compteur baisse de 1.", M + 392, hy - 54, W - M - 392 - 14, SANS, 8.4, INK2, 11.2)
    yy = hy - 124
    tip_box(c, M, yy, (W - 2 * M) / 2 - 8, "Une bonne photo de pièce",
            "Posée à plat sur une table, bien éclairée, la pièce entière visible, sans reflet. "
            "Si la photo est floue, le site la refuse tout de suite et le voyageur recommence.", EM, "#e8f3ef", EM_D)
    tip_box(c, M + (W - 2 * M) / 2 + 8, yy, (W - 2 * M) / 2 - 8, "Trois langues",
            "Le voyageur choisit français, anglais ou arabe au début. Il n'a besoin ni de compte ni de mot de passe.")


def page_review(c, a):
    page_bg(c)
    step_header(c, 5, "Contrôlez et confirmez", "Chaque fiche reçue apparaît dans « Fiches »")
    bx, by, bw, bh = M, H - 400, W - 2 * M, 240
    ix, iy, iw, ih = browser(c, bx, by, bw, bh, "…/admin/submissions")
    txt(c, "Fiches", ix + 16, iy + ih - 28, SERIF_B, 15, INK)
    rows = [("BENNANI Sara", "Appartement Agdal", "Validée par l'IA", "#e8f3ef", EM),
            ("DUBOIS Claire", "Riad Atlas", "À traiter", "#fdf4e3", "#8a5a0b"),
            ("GARCIA Luis", "Studio Médina", "Confirmée", "#e8f3ef", EM),
            ("MARTIN Paul", "Studio Médina", "Problème", "#fdecea", "#b42318")]
    for i, (nm, ap, st, bgc, fg) in enumerate(rows):
        yy = iy + ih - 76 - i * 40
        rrect(c, ix + 16, yy, iw - 32, 34, 8, WHITE, LINE, 0.8)
        txt(c, nm, ix + 28, yy + 20, SANS_B, 9, INK)
        txt(c, ap, ix + 28, yy + 8, SANS, 7.6, MUTED)
        chip(c, ix + iw - 130, yy + 10, st, bgc, fg, SANS_B, 7.4)
    callout(c, ix + iw - 22, iy + ih - 59, 1)
    # detail buttons
    yy = H - 440
    txt(c, "Dans une fiche", M, yy, SERIF_B, 16, INK)
    y = numbered(c, M, yy - 22, 285, [
        ("Ouvrez la fiche", "Touchez le nom du voyageur. Vous voyez ses informations et la photo de sa pièce."),
        ("Comparez", "Les informations écrites correspondent-elles à la pièce ? L'IA vous aide en signalant les différences."),
        ("Choisissez le logement", "S'il n'est pas encore choisi, touchez « Choisir le logement »."),
        ("Touchez « Confirmer la fiche »", "C'est terminé : le contrat est prêt."),
    ], 6)
    sx = M + 305
    shadow_card(c, sx, yy - 190, W - sx - M, 168, 14)
    txt(c, "Les statuts", sx + 16, yy - 42, SANS_B, 10.5, INK)
    sts = [("À traiter", "#fdf4e3", "#8a5a0b", "Nouvelle fiche à contrôler"),
           ("Validée par l'IA", "#e8f3ef", EM, "Tout est cohérent, il reste à confirmer"),
           ("Confirmée", "#e8f3ef", EM, "Fiche terminée, contrat disponible"),
           ("Problème", "#fdecea", "#b42318", "Une information ne correspond pas"),
           ("Archivée", SAND, INK2, "Rangée dans les archives")]
    for i, (n, bgc, fg, d) in enumerate(sts):
        chip(c, sx + 16, yy - 66 - i * 26, n, bgc, fg, SANS_B, 7.2)
        txt(c, d, sx + 16, yy - 76 - i * 26 + 0, SANS, 7.2, INK2) if False else None
        para(c, d, sx + 100, yy - 63 - i * 26, W - sx - M - 112, SANS, 7.4, INK2, 9)
    tip_box(c, M, yy - 214, W - 2 * M, "Vous restez le décideur",
            "L'IA est une aide : elle ne remplace jamais votre contrôle. En cas de doute, ne confirmez pas "
            "et contactez le voyageur pour qu'il corrige.", CLAY, "#fdf1ea", CLAY_D)


def page_pdfs(c, a):
    page_bg(c)
    step_header(c, 6, "Téléchargez votre contrat", "Un seul PDF, signé par le voyageur, prêt à imprimer")
    # the contract, drawn small
    x, y, w, h = M + 30, H - 392, 205, 240
    shadow_card(c, x, y, w, h, 6)
    c.drawImage(str(LOGO), x + 10, y + h - 34, 24, 24, mask="auto")
    txt(c, "CONTRAT DE LOCATION", x + 40, y + h - 20, SERIF_B, 8.2, CLAY)
    txt(c, "SAISONNIÈRE", x + 40, y + h - 29, SERIF_B, 8.2, CLAY)
    for k, lab in enumerate(("D'UNE PART — L'HÔTE", "D'AUTRE PART — LE VOYAGEUR")):
        bx = x + 10 + k * (w - 20) / 2
        rrect(c, bx, y + h - 78, (w - 28) / 2, 32, 3, "#fdf1ea", CLAY, 0.6)
        txt(c, lab, bx + 4, y + h - 55, SANS_B, 3.9, CLAY)
        for m in range(3):
            rrect(c, bx + 4, y + h - 62 - m * 5, 40 - m * 6, 2, 1, "#c9b9a3")
    for k in range(15):
        rrect(c, x + 10, y + h - 92 - k * 7.4, w - 20 - (k % 4) * 14, 2.6, 1.3, "#e6dac8")
    rrect(c, x + 10, y + 10, w - 20, 40, 3, None, CLAY, 0.7)
    txt(c, "Signature électronique du Voyageur", x + 14, y + 41, SANS_B, 4.2, CLAY)
    c.setStrokeColor(INK)
    c.setLineWidth(1)
    pth = c.beginPath()
    pth.moveTo(x + 16, y + 22)
    pth.curveTo(x + 26, y + 36, x + 34, y + 14, x + 46, y + 28)
    pth.curveTo(x + 54, y + 36, x + 62, y + 16, x + 76, y + 26)
    c.drawPath(pth, stroke=1, fill=0)
    txt(c, "Cachet de l'Hôte", x + w - 62, y + 41, SANS_B, 4.2, CLAY)
    sx = x + w + 40
    txt(c, "Dans la fiche :", sx, H - 188, SANS_B, 10, INK)
    button(c, sx, H - 230, 150, 26, "Contrat de location (PDF)", CLAY, size=8.2)
    callout(c, sx + 160, H - 217, 1)
    para(c, "Un bouton à droite de la fiche confirmée. Le contrat est rempli avec les informations du voyageur.",
         sx, H - 256, W - sx - M, SANS, 8.8, INK2, 12)
    yy = H - 420
    txt(c, "Ce que contient votre contrat", M, yy, SERIF_B, 16, INK)
    shadow_card(c, M, yy - 134, W - 2 * M, 118, 14)
    tile(c, M + 34, yy - 50, icon_doc, EM, 18)
    cols = (["Identité complète du voyageur", "Logement, dates et nombre de voyageurs", "Vos coordonnées d'hôte (Mon profil)", "Responsabilité du titulaire pour ses accompagnants"],
            ["10 règles de la maison (horaires, pas de sous-location…)", "Signature électronique du voyageur", "Une seule page, prête à imprimer", "Espace pour votre cachet"])
    for ci, items in enumerate(cols):
        for k, it in enumerate(items):
            bxx = M + 66 + ci * 235
            disc(c, bxx, yy - 36 - k * 21, 3, GOLD)
            for li, ln in enumerate(simpleSplit(it, SANS, 8.8, 215)):
                txt(c, ln, bxx + 9, yy - 39 - k * 21 - li * 9, SANS, 8.8, INK2)
    cy0 = yy - 160
    shadow_card(c, M, cy0 - 150, W - 2 * M, 150, 14)
    txt(c, "Le calendrier : vos arrivées du mois", M + 18, cy0 - 26, SERIF_B, 14, INK)
    gx, gy, cell = M + 18, cy0 - 50, 30
    for d, nm in enumerate(("L", "M", "M", "J", "V", "S", "D")):
        txt(c, nm, gx + d * cell + cell / 2 - 2, gy, SANS_B, 7.4, MUTED)
    marks = {2: EM, 5: CLAY, 9: EM, 12: GOLD, 16: CLAY}
    for k in range(21):
        r_, c_ = divmod(k, 7)
        cx2, cy2 = gx + c_ * cell + cell / 2, gy - 18 - r_ * 26
        if k in marks:
            disc(c, cx2, cy2 + 3, 10, marks[k])
            txt(c, str(k + 1), cx2, cy2, SANS_B, 7.6, WHITE, "c")
        else:
            txt(c, str(k + 1), cx2, cy2, SANS, 7.6, INK2, "c")
    lx = gx + 7 * cell + 30
    for i, (colr, t) in enumerate(((EM, "Arrivée confirmée"), (CLAY, "Fiche à traiter"), (GOLD, "Séjour en cours"))):
        disc(c, lx + 5, cy0 - 62 - i * 20, 5, colr)
        txt(c, t, lx + 16, cy0 - 65 - i * 20, SANS, 8.8, INK2)
    para(c, "Touchez « Calendrier » dans le menu pour voir d'un coup d'œil qui arrive et quand.", lx, cy0 - 128, W - M - lx - 14, SANS, 8.4, MUTED, 11)
    tip_box(c, M, cy0 - 168, W - 2 * M, "Où retrouver une fiche plus tard ?",
            "Dans « Archives » pour les fiches rangées, et dans « Calendrier » pour voir les arrivées du mois. "
            "Gardez le contrat sur votre téléphone ou imprimez-le : à vous de choisir.", EM, "#e8f3ef", EM_D)


def page_pack(c, a):
    page_bg(c)
    step_header(c, icon_clock, "Votre pack de fiches", "Combien il vous en reste, et comment en reprendre")
    # countdown card
    cx, cy, cw, ch = M, H - 330, 300, 190
    rrect(c, cx, cy, cw, ch, 18, EM)
    star_pattern(c, cx, cy, cw, ch, GOLD, 0.3, 34)
    txt(c, "PACK DE BIENVENUE", cx + 20, cy + ch - 30, SANS_B, 9, GOLD2)
    txt(c, f"{TRIAL['fiches']}", cx + 20, cy + ch - 84, SERIF_B, 54, WHITE)
    txt(c, f"fiches sur {TRIAL['fiches']}", cx + 100, cy + ch - 80, SANS, 12, "#cfe9e0")
    rrect(c, cx + 20, cy + 62, cw - 40, 12, 6, "#0a4034")
    rrect(c, cx + 20, cy + 62, cw - 40, 12, 6, GOLD)
    txt(c, f"{TRIAL['days']} jours restants", cx + 20, cy + 36, SANS_B, 10, WHITE)
    txt(c, "Le compteur baisse de 1 à chaque voyageur", cx + 20, cy + 20, SANS, 8.4, "#cfe9e0")
    callout(c, cx + cw - 16, cy + ch - 18, 1)
    sx = M + 325
    y = H - 160
    txt(c, "Comment ça marche", sx, y, SANS_B, 11, INK)
    y = para(c, "Votre compteur est visible sur la page Aperçu et dans Mon pack.", sx, y - 16, W - sx - M, SANS, 9.2, INK2, 12.4)
    y = para(c, "Le pack s'arrête quand les fiches sont toutes utilisées, ou après 30 jours : le premier des deux.", sx, y - 6, W - sx - M, SANS, 9.2, INK2, 12.4)
    y = para(c, "Un message vous prévient avant d'arriver à zéro.", sx, y - 6, W - sx - M, SANS, 9.2, INK2, 12.4)
    tip_box(c, sx, y - 6, W - sx - M, "Quand le pack est fini",
            "Vos voyageurs voient un message poli et ne peuvent plus s'enregistrer. Vos anciennes fiches restent consultables.",
            CLAY, "#fdf1ea", CLAY_D)
    yy = H - 372
    txt(c, "Reprendre un pack en 4 étapes", M, yy, SERIF_B, 16, INK)
    steps = [("Touchez « Mon pack »", "Choisissez l'offre qui vous convient."),
             ("Faites le virement", "Les coordonnées bancaires s'affichent dans le site, avec votre numéro de commande."),
             ("Envoyez votre reçu", "Prenez le reçu en photo et envoyez-le depuis la commande."),
             ("C'est activé", "Dès que nous avons vérifié votre paiement, vos fiches arrivent.")]
    cw2 = (W - 2 * M - 36) / 4
    for i, (t, b) in enumerate(steps):
        x = M + i * (cw2 + 12)
        shadow_card(c, x, yy - 116, cw2, 94, 12)
        badge(c, x + 18, yy - 38, i + 1, 10, CLAY)
        for k, ln in enumerate(simpleSplit(t, SANS_B, 8.6, cw2 - 40)):
            txt(c, ln, x + 34, yy - 36 - k * 10.5, SANS_B, 8.6, INK)
        para(c, b, x + 12, yy - 66, cw2 - 22, SANS, 7.8, INK2, 10)
        if i < 3:
            arrow(c, x + cw2 + 1, yy - 70, x + cw2 + 11, yy - 70, CLAY2, 1.4)
    # price table
    ty = yy - 142
    txt(c, "Les offres", M, ty, SERIF_B, 15, INK)
    rows = [(p["name"], p["audience"], f"{p['fiches']} fiches", f"{p['price']} DH") for p in PACKS.values()]
    rows.append(("Recharge", "En plus de votre pack", f"+{TOPUP['fiches']} fiches", f"{TOPUP['price']} DH"))
    rh = 21
    rrect(c, M, ty - 18 - rh * len(rows) - 6, W - 2 * M, rh * len(rows) + 8, 10, WHITE, LINE, 0.8)
    for i, (n, aud, fi, pr) in enumerate(rows):
        yy2 = ty - 18 - rh * (i + 1) + 6
        if i % 2 == 0:
            col(c, "#fbf3e6")
            c.rect(M + 1, yy2 - 6, W - 2 * M - 2, rh, fill=1, stroke=0)
        txt(c, n, M + 14, yy2, SANS_B, 9, INK)
        txt(c, aud, M + 150, yy2, SANS, 8.6, INK2)
        txt(c, fi, M + 330, yy2, SANS_B, 9, EM)
        txt(c, pr, W - M - 14, yy2, SANS_B, 9.6, CLAY, "r")
    txt(c, "Chaque pack est valable 2 mois. Si vous le renouvelez avant la fin, les fiches non utilisées sont reportées.",
        M, ty - 22 - rh * len(rows) - 12, SANS, 8.2, MUTED)


def page_help(c, a):
    page_bg(c)
    step_header(c, icon_chat, "Un souci ? On vous aide", "Les questions les plus fréquentes")
    qa = [
        ("Mon voyageur dit que le lien ne marche pas",
         "Vérifiez dans « Mon pack » qu'il vous reste des fiches et que le pack n'est pas expiré. Vérifiez aussi que vous n'avez pas généré un nouveau lien depuis."),
        ("La photo de la pièce est refusée",
         "Elle est floue, trop sombre ou coupée. Demandez au voyageur de la reprendre à plat sur une table, avec de la lumière, pièce entière visible."),
        ("Je n'arrive pas à confirmer une fiche",
         "Choisissez d'abord le logement (« Choisir le logement »). Si aucun logement n'existe, ajoutez-en un dans « Logements »."),
        ("Je veux supprimer ou ranger une fiche",
         "Ouvrez la fiche puis touchez « Archiver ». Elle ira dans « Archives »."),
        ("J'ai oublié mon mot de passe",
         "Écrivez-nous sur WhatsApp : nous vous en donnons un nouveau, que vous changerez ensuite."),
    ]
    y = H - 150
    for i, (q, ans) in enumerate(qa):
        lines = simpleSplit(ans, SANS, 9, W - 2 * M - 52)
        h = 30 + len(lines) * 12
        shadow_card(c, M, y - h, W - 2 * M, h, 10)
        badge(c, M + 18, y - 17, "?" if False else i + 1, 9, [EM, CLAY, GOLD, BLUE, EM][i])
        txt(c, q, M + 36, y - 20, SANS_B, 9.8, INK)
        yy = y - 34
        for ln in lines:
            txt(c, ln, M + 36, yy, SANS, 9, INK2)
            yy -= 12
        y -= h + 9
    # whatsapp box
    num = get_settings().support_whatsapp
    pretty = f"+{num[:3]} {num[3:6]} {num[6:9]} {num[9:]}" if len(num) == 12 else (f"+{num}" if num else "")
    y -= 4
    rrect(c, M, y - 70, W - 2 * M, 70, 14, "#1f9d55")
    tile(c, M + 38, y - 35, icon_chat, "#17824a", 20)
    txt(c, "Support WhatsApp", M + 72, y - 30, SERIF_B, 17, WHITE)
    if pretty:
        txt(c, f"Écrivez-nous au {pretty}", M + 72, y - 50, SANS_B, 11, "#e4f7ec")
    txt(c, "Réponse rapide, en français ou en arabe", W - M - 14, y - 40, SANS, 8.6, "#e4f7ec", "r")
    y -= 96
    txt(c, "Votre liste pour le premier jour", M, y, SERIF_B, 16, INK)
    todo = ["Je me connecte et je change mon mot de passe", "J'ajoute tous mes logements",
            "Je copie mon lien et je télécharge mon QR code", "Je fais un essai avec ma propre fiche",
            "J'envoie mon lien à mon prochain voyageur"]
    for i, t in enumerate(todo):
        yy = y - 26 - i * 22
        rrect(c, M, yy - 5, 14, 14, 3, WHITE, EM, 1.4)
        txt(c, t, M + 24, yy - 1, SANS, 10, INK2)
    zstrip(c, 46, 14)


PAGES = [page_cover, page_overview, page_login, page_apartments, page_link, page_guest, page_review, page_pdfs, page_pack, page_help]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name")
    ap.add_argument("--username")
    ap.add_argument("--slug")
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", default="https://tigmihostshield.duckdns.org")
    a = ap.parse_args()
    a.link = f"{a.base.rstrip('/')}/register/{a.slug}" if a.slug else None
    c = canvas.Canvas(a.out, pagesize=A4)
    c.setTitle(f"Guide de démarrage — {a.name}" if a.name else "Guide de démarrage — Tigmi Host Shield")
    c.setAuthor("Tigmi Host Shield")
    total = len(PAGES)
    for n, fn in enumerate(PAGES, 1):
        fn(c, a)
        if n > 1:
            footer(c, n, total)
        c.showPage()
    c.save()
    print("OK", a.out)


if __name__ == "__main__":
    main()
