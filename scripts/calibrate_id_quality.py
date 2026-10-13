#!/usr/bin/env python3
"""Calibrate / regression-test the ID image checks in app/services/id_quality.py.

Rule of thumb being tested: anything that is not an ID is refused ("not_id"); real IDs pass
unless they are clearly unusable (tiny, clearly blurry, very dark, overexposed, glare).

Builds synthetic phone photos of an ID card (fine print, portrait, guilloche, MRZ) lying at an
angle on different surfaces, with camera noise and JPEG compression, then applies each failure
mode. Prints the measured metrics and how many photos each condition accepts.

    .venv/bin/python scripts/calibrate_id_quality.py            # summary table
    .venv/bin/python scripts/calibrate_id_quality.py --metrics  # plus sharpness distribution
"""

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.services.id_quality import check_id_image, sharpness

SAMPLES = 10
PHOTO_W, PHOTO_H = 2000, 1500  # landscape phone photo (3 MP)


def _font(size: int):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def make_card(rng: random.Random, portrait_doc: bool = False) -> np.ndarray:
    w, h = (1420, 1000) if portrait_doc else (1712, 1080)  # passport page 1.42, ID-1 card 1.585
    base = tuple(rng.randint(185, 235) for _ in range(3))
    im = Image.new("RGB", (w, h), base)
    d = ImageDraw.Draw(im)
    for i in range(0, w, 6):  # guilloche-like fine lines
        d.arc([i - 300, -200, i + 300, h + 200], 0, 360, fill=tuple(max(0, c - 25) for c in base), width=1)
    d.rectangle([0, 0, w, 120], fill=(40, 70, 120))
    d.text((40, 35), "ROYAUME DU MAROC · CARTE NATIONALE D'IDENTITE", fill="white", font=_font(40))
    px0, py0 = 60, 170
    d.rectangle([px0, py0, px0 + 380, py0 + 480], fill=(150, 160, 170))
    d.ellipse([px0 + 110, py0 + 80, px0 + 270, py0 + 260], fill=(120, 95, 80))
    d.rectangle([px0 + 70, py0 + 280, px0 + 310, py0 + 480], fill=(60, 60, 80))
    y = 180
    for label, value in [("Nom / Surname", "BENALI"), ("Prénom / Given name", "SARA"), ("Né(e) le", "04.03.1990"),
                         ("Lieu", "MARRAKECH"), ("N° / No.", "ZZ998877"), ("Valable jusqu'au", "12.08.2031")]:
        d.text((500, y), label, fill=(70, 70, 90), font=_font(26))
        d.text((500, y + 30), value, fill=(15, 15, 30), font=_font(44))
        y += 95
    for i in range(6):  # fine print
        d.text((500, 760 + i * 22), "Ce document est la propriété de l'État. Toute falsification est punie par la loi." * 2,
               fill=(90, 90, 100), font=_font(16))
    d.text((40, h - 110), "IDMAR<ZZ998877<<<<<<<<<<<<<<<<<<<<<<<<", fill=(20, 20, 20), font=_font(46))
    d.text((40, h - 55), "9003045F3108123MAR<<<<<<<<<<<<<<<<<<<<6", fill=(20, 20, 20), font=_font(46))
    arr = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    if portrait_doc:
        arr = cv2.rotate(arr, cv2.ROTATE_90_CLOCKWISE)
    return arr


def background(rng: random.Random, kind: str, size=None) -> np.ndarray:
    w, h = size or (PHOTO_W, PHOTO_H)
    if kind == "wood":
        x = np.linspace(0, 40 * np.pi, w)
        stripes = (np.sin(x[None, :] + rng.random() * 6 + np.random.default_rng(rng.randint(0, 9999)).normal(0, 0.4, (h, 1))) + 1) / 2
        b = np.stack([60 + 40 * stripes, 90 + 50 * stripes, 130 + 60 * stripes], axis=-1)
    elif kind == "dark":
        b = np.full((h, w, 3), (45, 42, 40), float)
    elif kind == "light":
        b = np.full((h, w, 3), (150, 155, 160), float)
    else:  # fabric
        yy, xx = np.mgrid[0:h, 0:w]
        b = np.stack([90 + 25 * np.sin(xx / 7.0) * np.sin(yy / 7.0)] * 3, axis=-1) * np.array([0.8, 0.9, 1.2])
    noise = np.random.default_rng(rng.randint(0, 9999)).normal(0, 6, (h, w, 3))
    return np.clip(b + noise, 0, 255).astype(np.uint8)


def compose(rng: random.Random, *, fill=(0.35, 0.65), bg="wood", portrait_doc=False, cut=False, size=None) -> np.ndarray:
    global PHOTO_W, PHOTO_H
    saved = (PHOTO_W, PHOTO_H)
    if size:
        PHOTO_W, PHOTO_H = size
    try:
        return _compose(rng, fill=fill, bg=bg, portrait_doc=portrait_doc, cut=cut)
    finally:
        PHOTO_W, PHOTO_H = saved


def _compose(rng: random.Random, *, fill, bg, portrait_doc, cut) -> np.ndarray:
    card = make_card(rng, portrait_doc)
    ch, cw = card.shape[:2]
    photo = background(rng, bg)
    target_area = rng.uniform(*fill) * PHOTO_W * PHOTO_H
    scale = (target_area / (cw * ch)) ** 0.5
    sw, sh = cw * scale, ch * scale
    cx = rng.uniform(sw / 2 + 60, PHOTO_W - sw / 2 - 60) if PHOTO_W - sw > 140 else PHOTO_W / 2
    cy = rng.uniform(sh / 2 + 60, PHOTO_H - sh / 2 - 60) if PHOTO_H - sh > 140 else PHOTO_H / 2
    if cut:
        cx = PHOTO_W - sw / 2 + sw * 0.18
    angle = np.deg2rad(rng.uniform(-8, 8))
    corners = np.array([[-sw / 2, -sh / 2], [sw / 2, -sh / 2], [sw / 2, sh / 2], [-sw / 2, sh / 2]])
    rot = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    dst = corners @ rot.T + [cx, cy]
    dst += np.random.default_rng(rng.randint(0, 9999)).normal(0, 0.025 * sw, dst.shape)  # perspective tilt
    if not cut:  # keep every corner at least 3% inside the frame, like a careful guest would
        mx, my = 0.03 * PHOTO_W, 0.03 * PHOTO_H
        lo, hi = dst.min(axis=0), dst.max(axis=0)
        span = np.array([PHOTO_W - 2 * mx, PHOTO_H - 2 * my])
        shrink = min(1.0, *(span / (hi - lo)))
        dst = (dst - (lo + hi) / 2) * shrink + (lo + hi) / 2
        lo, hi = dst.min(axis=0), dst.max(axis=0)
        dst += np.maximum(0, np.array([mx, my]) - lo) - np.maximum(0, hi - np.array([PHOTO_W - mx, PHOTO_H - my]))
    m = cv2.getPerspectiveTransform(np.float32([[0, 0], [cw, 0], [cw, ch], [0, ch]]), np.float32(dst))
    warped = cv2.warpPerspective(card, m, (PHOTO_W, PHOTO_H))
    mask = cv2.warpPerspective(np.full((ch, cw), 255, np.uint8), m, (PHOTO_W, PHOTO_H))
    shadow = cv2.GaussianBlur(cv2.dilate(mask, np.ones((25, 25), np.uint8)), (61, 61), 0)[..., None] / 255.0
    photo = (photo * (1 - 0.35 * shadow)).astype(np.uint8)
    photo[mask > 0] = warped[mask > 0]
    return photo


def camera(img: np.ndarray, rng: random.Random, *, blur=0.0, motion=0, gain=1.0, glare=False, noise=5.0) -> np.ndarray:
    out = img.astype(np.float32)
    if glare:
        h, w = out.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w]
        cx, cy = rng.uniform(0.35, 0.65) * w, rng.uniform(0.35, 0.65) * h
        spot = np.exp(-(((xx - cx) / (0.13 * w)) ** 2 + ((yy - cy) / (0.13 * h)) ** 2))
        out = out + 400 * spot[..., None]
    out = out * gain
    if blur > 0:
        out = cv2.GaussianBlur(out, (0, 0), blur)
    if motion:
        k = np.zeros((motion, motion), np.float32)
        k[motion // 2, :] = 1.0 / motion
        out = cv2.filter2D(out, -1, k)
    out = out + np.random.default_rng(rng.randint(0, 9999)).normal(0, noise, out.shape)
    out = np.clip(out, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes()


CONDITIONS = [
    # name, expected, compose kwargs, camera kwargs
    ("clear · wood table", "ok", {"bg": "wood"}, {}),
    ("clear · dark table", "ok", {"bg": "dark"}, {}),
    ("clear · light table", "ok", {"bg": "light"}, {}),
    ("clear · fabric", "ok", {"bg": "fabric"}, {}),
    ("clear · passport page (portrait)", "ok", {"bg": "wood", "portrait_doc": True}, {}),
    ("clear · noisy (low light sensor)", "ok", {"bg": "dark"}, {"noise": 10}),
    ("clear · slightly soft (σ 1.0)", "ok", {"bg": "wood"}, {"blur": 1.0}),
    ("blurry σ 2.0", "blurry|not_id", {"bg": "wood"}, {"blur": 2.0}),
    ("blurry σ 3.0", "blurry|not_id", {"bg": "dark"}, {"blur": 3.0}),
    ("blurry σ 5.0", "blurry|not_id", {"bg": "light"}, {"blur": 5.0}),
    ("blurry σ 2.5 + noise", "blurry|not_id", {"bg": "wood"}, {"blur": 2.5, "noise": 10}),
    ("hand shake (motion 15px)", "ok|blurry|not_id", {"bg": "wood"}, {"motion": 15}),
    ("too dark", "too_dark|not_id", {"bg": "dark"}, {"gain": 0.25}),
    ("overexposed", "too_bright|not_id", {"bg": "light"}, {"gain": 1.9}),
    ("flash glare", "glare|not_id", {"bg": "wood"}, {"glare": True}),
    ("corner cut off (accepted when the ID is still recognisable)", "ok|not_id", {"bg": "wood", "fill": (0.4, 0.6), "cut": True}, {}),
    ("too far away", "ok|not_id", {"bg": "wood", "fill": (0.06, 0.14)}, {}),
    ("too far away · 3:2 photo", "ok|not_id", {"bg": "wood", "fill": (0.06, 0.14), "size": (2100, 1400)}, {}),
]


def no_document(rng: random.Random) -> bytes:
    return camera(background(rng, rng.choice(["wood", "dark", "fabric"])), rng)


def cropped(width: int, blur: float = 0.0, portrait_doc: bool = False):
    """An image cropped exactly to the document (scan / edited photo), resized to `width`."""
    def make(rng: random.Random) -> bytes:
        card = make_card(rng, portrait_doc)
        if blur:
            card = cv2.GaussianBlur(card, (0, 0), blur)
        h, w = card.shape[:2]
        f = width / max(h, w)
        card = cv2.resize(card, (int(w * f), int(h * f)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", card, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return buf.tobytes()
    return make


def no_document_3x2(rng: random.Random) -> bytes:
    return camera(background(rng, rng.choice(["wood", "dark", "fabric"]), size=(2100, 1400)), rng)


def main() -> None:
    show_metrics = "--metrics" in sys.argv
    rng = random.Random(7)
    print(f"{'condition':38} {'expected':11} {'result':>8}   codes")
    all_good = True
    sharp_by_cond = {}
    for name, expected, ck, camk in CONDITIONS:
        codes, sharps, surrounds = [], [], []
        for _ in range(SAMPLES):
            res = check_id_image(camera(compose(rng, **ck), rng, **camk), "photo.jpg")
            codes.append(res.code)
            if "sharpness" in res.metrics:
                sharps.append(res.metrics["sharpness"])
            if "surround" in res.metrics:
                surrounds.append(res.metrics["surround"])
        hits = sum(c in expected.split("|") for c in codes)
        all_good &= hits == SAMPLES
        summary = ", ".join(f"{c}×{codes.count(c)}" for c in sorted(set(codes)))
        print(f"{name:38} {expected:11} {hits:>3}/{SAMPLES}   {summary}")
        sharp_by_cond[name] = sharps
        if show_metrics and surrounds:
            print(f"{'':38} surround ratio max {max(surrounds):.2f}")
    def gradient(rng):
        g = np.dstack([np.tile(np.linspace(0, 255, 900), (600, 1))] * 3).astype(np.uint8)
        return cv2.imencode(".jpg", g)[1].tobytes()

    def noise_img(rng):
        return cv2.imencode(".jpg", np.random.default_rng(rng.randint(0, 999)).integers(0, 255, (600, 900, 3), dtype=np.uint8))[1].tobytes()

    def text_page(rng):
        im = Image.new("RGB", (1240, 1754), "white")
        d = ImageDraw.Draw(im)
        for i in range(40):
            d.text((80, 80 + i * 40), "Lorem ipsum dolor sit amet, consectetur adipiscing elit sed do eiusmod", fill="black", font=_font(28))
        return cv2.imencode(".jpg", cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR))[1].tobytes()

    def landscape(rng):
        sc = np.zeros((900, 1600, 3), np.uint8)
        sc[:450], sc[450:] = (235, 180, 120), (60, 120, 70)
        return cv2.imencode(".jpg", sc)[1].tobytes()

    for name, expected, fn in [("random · just a table", "not_id", no_document),
                               ("random · table, 3:2 photo", "not_id", no_document_3x2),
                               ("random · gradient", "not_id", gradient),
                               ("random · noise", "not_id", noise_img),
                               ("random · page of ordinary text", "not_id", text_page),
                               ("random · landscape", "not_id", landscape),
                               ("cropped card · 1712 px", "ok", cropped(1712)),
                               ("cropped card · 900 px", "ok", cropped(900)),
                               ("cropped card · 640 px", "ok", cropped(640)),
                               ("cropped card · 500 px", "ok", cropped(500)),
                               ("cropped passport page · 1000 px", "ok", cropped(1000, portrait_doc=True)),
                               ("cropped card blurry σ 3 · 1000 px", "blurry|not_id", cropped(1000, blur=3.0)),
                               ("cropped card blurry σ 6 · 1000 px", "blurry|not_id", cropped(1000, blur=6.0))]:
        codes = [check_id_image(fn(rng), "photo.jpg").code for _ in range(SAMPLES)]
        hits = sum(c in expected.split("|") for c in codes)
        all_good &= hits == SAMPLES
        print(f"{name:38} {expected:11} {hits:>3}/{SAMPLES}   " + ", ".join(f"{c}×{codes.count(c)}" for c in sorted(set(codes))))
    # Optional real ID images (not in git): scripts/samples/real_ids/*.jpg must all pass
    real_dir = ROOT / "scripts" / "samples" / "real_ids"
    for f in sorted(real_dir.glob("*.*")) if real_dir.exists() else []:
        code = check_id_image(f.read_bytes(), f.name).code
        all_good &= code == "ok"
        print(f"{'real ID · ' + f.name:38} {'ok':11} {'1/1' if code == 'ok' else '0/1':>5}   {code}")
    tiny = cv2.imencode(".jpg", np.full((100, 150, 3), 200, np.uint8))[1].tobytes()
    print(f"{'tiny image 150×100':38} {'too_small':11} {'1/1' if check_id_image(tiny).code == 'too_small' else '0/1':>5}")
    print(f"{'not an image':38} {'unreadable':11} {'1/1' if check_id_image(b'hello', 'x.jpg').code == 'unreadable' else '0/1':>5}")
    if show_metrics:
        print("\nSharpness (variance of Laplacian on flattened document):")
        for name, vals in sharp_by_cond.items():
            if vals:
                print(f"  {name:38} min {min(vals):7.1f}  median {sorted(vals)[len(vals)//2]:7.1f}  max {max(vals):7.1f}")
    print("\nALL CONDITIONS AS EXPECTED" if all_good else "\nSOME CONDITIONS MISMATCH — adjust thresholds")


if __name__ == "__main__":
    main()
