"""Checks that a guest's upload is a real, usable identity document — without being fussy.

The main rule: the image must LOOK LIKE AN ID — a portrait photo placed to one side as on ID
cards and passports (not a centred selfie), or ID-style printed text (machine-readable zone,
dates, "identity / passport / carte…") spread across the document. That keeps random pictures out.
Then only clear problems are refused: tiny, clearly blurry, very dark, overexposed or glare.

Photos of a document on a table are flattened to the document first (its 4 edges are found);
scans or images cropped to the document are checked as they are.
Thresholds are calibrated with scripts/calibrate_id_quality.py.
"""

import re
from dataclasses import dataclass, field

import cv2
import numpy as np

# --- Thresholds (see scripts/calibrate_id_quality.py) ---
MIN_LONG_SIDE = 200             # px: below this nothing can be checked (web thumbnails ~250 px are fine)
WORK_LONG_SIDE = 1200           # analysis size for photos
MIN_DOC_AREA = 0.20             # a found outline must cover >= 20% of the photo to be used
MAX_DOC_AREA = 0.97
BORDER_MARGIN = 0.01
ASPECT_MIN, ASPECT_MAX = 1.25, 1.90   # ID-1 card 1.59, passport page 1.42 (with some perspective)
RECTANGULARITY_MIN = 0.85
WARP_WIDTH = 1000               # documents are measured at this width (smaller images: at their own size)
ID_VIEW_LONG_SIDE = 1000        # documents are looked at this size for the portrait / text check
SHARPNESS_MIN = 40.0            # variance of Laplacian; refuses clearly blurry images only
DARK_MEAN_MAX = 50
BRIGHT_MEAN_MIN = 240
GLARE_FRACTION_MAX = 0.10
FACE_MIN, FACE_MAX = 0.16, 0.80          # portrait height / document short side
FACE_CENTRE_BAND = (0.40, 0.60)          # a face centred here is a selfie, not an ID portrait
TEXT_WORDS_MIN = 5
TEXT_SPAN_MIN = 0.45
ID_TEXT = re.compile(
    r"<<|\b\d{2}[./-]\d{2}[./-]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b|IDENTI|PASSPORT|PASSEPORT|CARTE|CARD|NATIONAL|"
    r"REPUBLI|ROYAUME|KINGDOM|PERMIS|DRIVING|LICEN|SURNAME|GIVEN|NOM|PR[EÉ]NOM|BIRTH|NAISSANCE|SEX|EXPIR|VALID",
    re.IGNORECASE,
)

MESSAGES = {
    "unreadable": "We could not read this file. Please upload a JPG or PNG photo, or a PDF.",
    "too_small": "The image is too small to check. Upload a larger photo or scan of your ID.",
    "not_id": "We can't recognise an identity document in this image. Upload a clear, sharp photo or scan of your passport or ID card — the side with your photo.",
    "blurry": "The image is blurry. Hold your phone steady, tap to focus on the document, and take it again.",
    "too_dark": "The image is too dark. Take it in a brighter place.",
    "too_bright": "The image is overexposed. Avoid direct sunlight or flash.",
    "glare": "There is a strong reflection on the document. Tilt it slightly or turn off the flash.",
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


def _views(doc: np.ndarray) -> list[np.ndarray]:
    """Grey copies at a size where faces and print are easy to find; sideways images in both rotations."""
    h, w = doc.shape[:2]
    f = ID_VIEW_LONG_SIDE / max(h, w)
    interp = cv2.INTER_CUBIC if f > 1 else cv2.INTER_AREA
    gray = cv2.cvtColor(cv2.resize(doc, (int(w * f), int(h * f)), interpolation=interp), cv2.COLOR_BGR2GRAY)
    if w >= h:
        return [gray]
    return [cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE), cv2.rotate(gray, cv2.ROTATE_90_COUNTERCLOCKWISE)]


def _has_id_portrait(gray: np.ndarray) -> bool:
    """A face the size of an ID portrait, placed to one side of the document (not a centred selfie)."""
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    h, w = gray.shape
    short = min(h, w)
    faces = cascade.detectMultiScale(
        cv2.equalizeHist(gray), scaleFactor=1.08, minNeighbors=5,
        minSize=(int(FACE_MIN * short),) * 2, maxSize=(int(FACE_MAX * short),) * 2,
    )
    lo, hi = FACE_CENTRE_BAND
    return any(not lo <= (x + fw / 2) / w <= hi for x, y, fw, fh in faces)


def _has_id_text(gray: np.ndarray) -> bool:
    """ID-style words (MRZ, dates, identity/passport…) spread across the document."""
    try:
        import pytesseract

        from app.services.ai_local import _configure_tesseract

        _configure_tesseract()
        data = pytesseract.image_to_data(gray, config="--psm 11", output_type=pytesseract.Output.DICT)
    except Exception:
        return False
    h, w = gray.shape
    boxes, words = [], []
    for text, conf, x, y, bw, bh in zip(
        data["text"], data["conf"], data["left"], data["top"], data["width"], data["height"]
    ):
        text = (text or "").strip()
        if len("".join(ch for ch in text if ch.isalnum())) >= 3 and float(conf) >= 45:
            boxes.append((x, y, x + bw, y + bh))
            words.append(text)
    if len(boxes) < TEXT_WORDS_MIN or not ID_TEXT.search(" ".join(words)):
        return False
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    return (x1 - x0) >= TEXT_SPAN_MIN * w and (y1 - y0) >= TEXT_SPAN_MIN * h


def looks_like_id(doc: np.ndarray) -> bool:
    return any(_has_id_portrait(v) or _has_id_text(v) for v in _views(doc))


def _quality(doc: np.ndarray, metrics: dict) -> IdQualityResult | None:
    """Clear exposure / sharpness problems on the document, or None when fine."""
    gray = cv2.cvtColor(doc, cv2.COLOR_BGR2GRAY)
    mean = float(gray.mean())
    sharp = sharpness(gray)
    glare = float((doc.min(axis=2) >= 245).mean())
    metrics.update(sharpness=round(sharp, 1), brightness=round(mean, 1), glare=round(glare, 3))
    if mean < DARK_MEAN_MAX:
        return _fail("too_dark", **metrics)
    if mean > BRIGHT_MEAN_MIN:
        return _fail("too_bright", **metrics)
    if metrics.get("mode") == "photo" and glare > GLARE_FRACTION_MAX:  # white scan margins are not glare
        return _fail("glare", **metrics)
    if sharp < SHARPNESS_MIN:
        return _fail("blurry", **metrics)
    return None


def check_id_image(data: bytes, filename: str = "") -> IdQualityResult:
    original = _decode(data, filename)
    if original is None or original.size == 0:
        return _fail("unreadable")
    h, w = original.shape[:2]
    if max(h, w) < MIN_LONG_SIDE:
        return _fail("too_small", width=w, height=h)

    metrics = {"width": w, "height": h}
    # Candidates: the document flattened from a photo (if an outline is found), then the whole image
    # (scans, cropped images, or an outline that was really a box printed on the card).
    candidates = []
    scale = min(1.0, WORK_LONG_SIDE / max(h, w))
    img = cv2.resize(original, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else original
    corners, area_share = _find_document(img)
    if corners is not None and MIN_DOC_AREA <= area_share <= MAX_DOC_AREA:
        candidates.append((_flatten(img, corners), {"mode": "photo", "doc_area": round(area_share, 3)}))
    f = min(1.0, WARP_WIDTH / max(h, w))
    whole = cv2.resize(original, (int(w * f), int(h * f)), interpolation=cv2.INTER_AREA) if f < 1 else original
    candidates.append((whole, {"mode": "image"}))

    # First: is it an ID at all? Random pictures are refused with that reason, nothing else.
    doc = None
    for cand, extra in candidates:
        if looks_like_id(cand):
            doc = cand
            metrics.update(extra)
            break
    if doc is None:
        return _fail("not_id", **metrics)
    problem = _quality(doc, metrics)
    if problem:
        return problem
    return IdQualityResult(ok=True, metrics=metrics)
