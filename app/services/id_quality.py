"""Strict quality checks for guest ID photos: readable, large enough, whole document visible
(4 edges detected), sharp, and well lit. Same rules for every upload; thresholds are
calibrated with scripts/calibrate_id_quality.py.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

# --- Thresholds (see scripts/calibrate_id_quality.py) ---
MIN_SHORT_SIDE = 480            # px, original image
MIN_LONG_SIDE = 800
WORK_LONG_SIDE = 1200           # analysis size
MIN_DOC_AREA = 0.20             # document must cover >= 20% of the photo
MAX_DOC_AREA = 0.97             # ... and leave a margin so its edges are visible
BORDER_MARGIN = 0.01            # corners must be >= 1% inside the frame (not cut off)
ASPECT_MIN, ASPECT_MAX = 1.25, 1.90   # ID-1 card 1.59, passport page 1.42 (with some perspective)
RECTANGULARITY_MIN = 0.85       # contour area / its bounding quad area
WARP_WIDTH = 1000               # document is flattened to this width before measuring
SHARPNESS_MIN = 65.0            # variance of Laplacian on the flattened, lightly denoised document
DARK_MEAN_MAX = 60              # mean brightness of the document below this = too dark
BRIGHT_MEAN_MIN = 235           # mean brightness above this = overexposed
GLARE_FRACTION_MAX = 0.06       # share of blown-out pixels on the document

MESSAGES = {
    "unreadable": "We could not read this file. Please upload a JPG or PNG photo, or a PDF.",
    "too_small": "The photo is too small. Use your phone camera at full resolution.",
    "no_document": "We can't see the 4 edges of your document. Place it flat on a plain, darker surface with all 4 corners visible, and make sure the photo is sharp.",
    "cut_off": "Part of the document is cut off. Move back a little so all 4 corners are inside the photo.",
    # Also returned when the photo is cropped so tightly that only a box printed on the card is found.
    "too_far": "We can't see the whole document clearly. Take the photo so the document fills most of the picture, with all 4 corners and a little of the table visible around it.",
    "blurry": "The photo is blurry. Hold your phone steady, tap to focus on the document, and take it again.",
    "too_dark": "The photo is too dark. Take it in a brighter place.",
    "too_bright": "The photo is overexposed. Avoid direct sunlight or flash.",
    "glare": "There is a reflection (glare) on the document. Tilt it slightly or turn off the flash.",
}


@dataclass
class IdQualityResult:
    ok: bool
    code: str = "ok"
    message: str = ""
    metrics: dict = field(default_factory=dict)


def _fail(code: str, **metrics) -> IdQualityResult:
    return IdQualityResult(ok=False, code=code, message=MESSAGES[code], metrics=metrics)


def _decode(data: bytes, filename: str) -> np.ndarray | None:
    if filename.lower().endswith(".pdf") or data[:5] == b"%PDF-":
        try:
            import fitz

            doc = fitz.open(stream=data, filetype="pdf")
            if doc.page_count < 1:
                return None
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(2.5, 2.5))
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR if pix.n == 4 else cv2.COLOR_RGB2BGR)
        except Exception:
            return None
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)  # applies EXIF orientation
    return img


def _order_corners(pts: np.ndarray) -> np.ndarray:
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)


DETECT_LONG_SIDE = 640          # outline search runs on a small copy: table/fabric texture fades out


def _quad_from_contour(c: np.ndarray, img_area: float) -> tuple[np.ndarray, float] | None:
    """A document-shaped 4-corner outline from a contour, or None."""
    area = cv2.contourArea(c)
    if area < 0.04 * img_area:
        return None
    hull = cv2.convexHull(c)
    hull_area = cv2.contourArea(hull)
    if hull_area <= 0:
        return None
    peri = cv2.arcLength(hull, True)
    quad = None
    for eps in (0.015, 0.02, 0.03, 0.04, 0.05):
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            quad = approx.reshape(4, 2).astype(np.float32)
            break
    if quad is None:
        # Rounded card corners or a slightly broken outline: fall back to the minimum-area rectangle
        rect = cv2.minAreaRect(hull)
        box = cv2.boxPoints(rect).astype(np.float32)
        if hull_area / max(cv2.contourArea(box), 1.0) < 0.92:
            return None
        quad = box
    quad_area = cv2.contourArea(quad)
    if quad_area <= 0 or hull_area / quad_area < RECTANGULARITY_MIN:
        return None
    corners = _order_corners(quad)
    tl, tr, br, bl = corners
    width = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2
    height = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2
    if min(width, height) <= 0:
        return None
    if not ASPECT_MIN <= max(width, height) / min(width, height) <= ASPECT_MAX:
        return None
    return corners, quad_area


def _candidate_masks(small: np.ndarray) -> list[np.ndarray]:
    """Binary images whose contours may outline the document (several strategies, all deterministic)."""
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB)
    smooth = cv2.bilateralFilter(gray, 9, 60, 60)
    masks = []
    close = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

    # 1) Edges of the smoothed image (works on most surfaces)
    median = float(np.median(smooth))
    edges = cv2.Canny(smooth, int(max(10, 0.5 * median)), int(min(255, max(40, 1.2 * median))))
    masks.append(cv2.morphologyEx(cv2.dilate(edges, close), cv2.MORPH_CLOSE, close, iterations=2))

    # 2) Edges of the colour channels (document vs table often differ in colour, not brightness)
    for ch in (lab[..., 1], lab[..., 2]):
        ch = cv2.GaussianBlur(ch, (5, 5), 0)
        e = cv2.Canny(ch, 8, 24)
        masks.append(cv2.morphologyEx(cv2.dilate(e, close), cv2.MORPH_CLOSE, close, iterations=2))

    # 3) Brightness segmentation (light document on a darker surface, or the reverse)
    _, otsu = cv2.threshold(cv2.GaussianBlur(gray, (7, 7), 0), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    big = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    for m in (otsu, 255 - otsu):
        masks.append(cv2.morphologyEx(cv2.morphologyEx(m, cv2.MORPH_CLOSE, big), cv2.MORPH_OPEN, big))
    return masks


def _find_document(img: np.ndarray) -> tuple[np.ndarray | None, float]:
    """Largest document-shaped 4-corner outline. Returns (corners in img coords, area share)."""
    h, w = img.shape[:2]
    f = DETECT_LONG_SIDE / max(h, w)
    small = cv2.resize(img, (max(1, int(w * f)), max(1, int(h * f))), interpolation=cv2.INTER_AREA)
    sh, sw = small.shape[:2]
    img_area = float(sh * sw)
    tol = 2.0  # px at detection size

    def edges_on_border(corners: np.ndarray) -> int:
        """How many of the 4 sides lie along the photo's own border."""
        on = [(x <= tol, y <= tol, x >= sw - 1 - tol, y >= sh - 1 - tol) for x, y in corners]
        sides = 0
        for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
            sides += any(on[a][k] and on[b][k] for k in range(4))
        return sides

    best, best_area = None, 0.0
    for mask in _candidate_masks(small):
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(contours, key=cv2.contourArea, reverse=True)[:12]:
            found = _quad_from_contour(c, img_area)
            if not found or edges_on_border(found[0]) >= 2:
                continue  # nothing, or (part of) the photo frame itself
            if found[1] > best_area:
                best, best_area = found
    if best is None:
        return None, 0.0
    return best / f, best_area / img_area


def _flatten(img: np.ndarray, corners: np.ndarray) -> np.ndarray:
    tl, tr, br, bl = corners
    width = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2
    height = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2
    if height > width:  # portrait document: keep it upright-ish but measure at a fixed size
        out_w, out_h = int(WARP_WIDTH * width / height), WARP_WIDTH
    else:
        out_w, out_h = WARP_WIDTH, int(WARP_WIDTH * height / width)
    dst = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(corners, dst)
    return cv2.warpPerspective(img, m, (out_w, out_h))


def sharpness(gray: np.ndarray) -> float:
    """Variance of the Laplacian after a light denoise (sensor noise must not count as detail)."""
    smoothed = cv2.GaussianBlur(gray, (3, 3), 0)
    return float(cv2.Laplacian(smoothed, cv2.CV_64F).var())


def check_id_image(data: bytes, filename: str = "") -> IdQualityResult:
    img = _decode(data, filename)
    if img is None or img.size == 0:
        return _fail("unreadable")

    h, w = img.shape[:2]
    if min(h, w) < MIN_SHORT_SIDE or max(h, w) < MIN_LONG_SIDE:
        return _fail("too_small", width=w, height=h)

    scale = WORK_LONG_SIDE / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    h, w = img.shape[:2]

    corners, area_share = _find_document(img)
    if corners is None:
        # Say why when we can: a very dark or washed-out photo also hides the edges.
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mean = float(gray.mean())
        if mean < DARK_MEAN_MAX / 2:
            return _fail("too_dark", brightness=round(mean, 1))
        if mean > BRIGHT_MEAN_MIN or float((gray >= 250).mean()) > 0.5:
            return _fail("too_bright", brightness=round(mean, 1))
        return _fail("no_document")

    margin_x, margin_y = BORDER_MARGIN * w, BORDER_MARGIN * h
    inside = all(margin_x <= x <= w - 1 - margin_x and margin_y <= y <= h - 1 - margin_y for x, y in corners)
    if not inside or area_share > MAX_DOC_AREA:
        return _fail("cut_off", doc_area=round(area_share, 3))
    if area_share < MIN_DOC_AREA:
        return _fail("too_far", doc_area=round(area_share, 3))

    doc = _flatten(img, corners)
    gray = cv2.cvtColor(doc, cv2.COLOR_BGR2GRAY)
    mean = float(gray.mean())
    sharp = sharpness(gray)
    glare = float((doc.min(axis=2) >= 245).mean())
    metrics = {
        "doc_area": round(area_share, 3),
        "sharpness": round(sharp, 1),
        "brightness": round(mean, 1),
        "glare": round(glare, 3),
    }

    if mean < DARK_MEAN_MAX:
        return _fail("too_dark", **metrics)
    if mean > BRIGHT_MEAN_MIN:
        return _fail("too_bright", **metrics)
    if glare > GLARE_FRACTION_MAX:
        return _fail("glare", **metrics)
    if sharp < SHARPNESS_MIN:
        return _fail("blurry", **metrics)
    return IdQualityResult(ok=True, metrics=metrics)
