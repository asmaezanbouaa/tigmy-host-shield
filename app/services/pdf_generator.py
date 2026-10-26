"""The signed rental contract (Contrat de location saisonnière), one A4 PDF per guest.

Layout: "Royaume du Maroc" letterhead (French left, Arabic right, coat of arms centred), a zellige
ornament rule, the TIGMI company logo (title row, footer, light watermark), the platform palette
(terracotta / zellige green / saffron) and a stamp box for the host.
"""

from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle
from reportlab.platypus.doctemplate import BaseDocTemplate, Frame, PageTemplate

from app.config import PROJECT_ROOT, get_settings
from app.models import Submission
from app.services.pdf_assets import ensure_coat_header_image, ensure_logo_assets

settings = get_settings()

# Platform palette
CLAY = colors.HexColor("#B8532D")
CLAY_DARK = colors.HexColor("#7A3319")
ZELLIGE = colors.HexColor("#1F6E5A")
SAFFRON = colors.HexColor("#D99A2B")
INK = colors.HexColor("#2B1F18")
INK_2 = colors.HexColor("#5C4A3F")
MUTED = colors.HexColor("#8A776A")
LINE = colors.HexColor("#E2D4C2")
SAND = colors.HexColor("#FBF7F1")
SAND_2 = colors.HexColor("#F5ECDF")
WHITE = colors.white

PAGE_W, PAGE_H = A4
MARGIN_L = MARGIN_R = 1.6 * cm
HEADER_H = 3.35 * cm
FOOTER_H = 1.9 * cm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R

AR_FONT, AR_FONT_BOLD = "NotoNaskhArabic", "NotoNaskhArabic-Bold"
_FONTS_READY = False


def _register_fonts() -> None:
    global _FONTS_READY
    if _FONTS_READY:
        return
    fonts = PROJECT_ROOT / "config" / "fonts"
    pdfmetrics.registerFont(TTFont(AR_FONT, str(fonts / "NotoNaskhArabic-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(AR_FONT_BOLD, str(fonts / "NotoNaskhArabic-Bold.ttf")))
    _FONTS_READY = True


def ar(text: str) -> str:
    """Arabic text in visual order with joined letters (for one line)."""
    import arabic_reshaper
    from bidi.algorithm import get_display

    return get_display(arabic_reshaper.reshape(text))


def _escape(text) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ")


def _styles() -> dict:
    base = dict(fontName="Helvetica", textColor=INK, leading=11)
    return {
        "label": ParagraphStyle("label", **{**base, "fontSize": 7.6, "textColor": INK_2}),
        "label_ar": ParagraphStyle("label_ar", fontName=AR_FONT, fontSize=8.5, leading=11, textColor=INK_2, alignment=TA_RIGHT),
        "value": ParagraphStyle("value", **{**base, "fontName": "Helvetica-Bold", "fontSize": 9}),
        "section": ParagraphStyle("section", **{**base, "fontName": "Helvetica-Bold", "fontSize": 8.5, "textColor": CLAY_DARK}),
        "section_ar": ParagraphStyle("section_ar", fontName=AR_FONT_BOLD, fontSize=9.5, leading=12, textColor=CLAY_DARK, alignment=TA_RIGHT),
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=14, leading=17, textColor=INK, alignment=TA_CENTER),
        "title_ar": ParagraphStyle("title_ar", fontName=AR_FONT_BOLD, fontSize=13, leading=18, textColor=CLAY_DARK, alignment=TA_CENTER),
        "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=7.8, leading=10, textColor=MUTED, alignment=TA_CENTER),
        "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=7.6, leading=10, textColor=INK_2),
        "meta_r": ParagraphStyle("meta_r", fontName="Helvetica", fontSize=7.6, leading=10, textColor=INK_2, alignment=TA_RIGHT),
        "notice": ParagraphStyle("notice", fontName="Helvetica-Oblique", fontSize=7.4, leading=10, textColor=INK_2, alignment=TA_JUSTIFY),
        "notice_ar": ParagraphStyle("notice_ar", fontName=AR_FONT, fontSize=8.4, leading=12, textColor=INK_2, alignment=TA_RIGHT),
        "article_inline": ParagraphStyle("article_inline", fontName="Helvetica", fontSize=7.8, leading=10.4, textColor=INK, alignment=TA_JUSTIFY, spaceAfter=2.6),
        "article_title": ParagraphStyle("article_title", fontName="Helvetica-Bold", fontSize=8.4, leading=11, textColor=CLAY_DARK, spaceBefore=5, spaceAfter=1.5),
        "article_body": ParagraphStyle("article_body", fontName="Helvetica", fontSize=7.9, leading=11, textColor=INK, alignment=TA_JUSTIFY, spaceAfter=2),
        "article_title_ar": ParagraphStyle("article_title_ar", fontName=AR_FONT_BOLD, fontSize=9.2, leading=12.4, textColor=CLAY_DARK, alignment=TA_RIGHT, spaceBefore=3.5, spaceAfter=0),
        "article_body_ar": ParagraphStyle("article_body_ar", fontName=AR_FONT, fontSize=8.5, leading=12.2, textColor=INK, alignment=TA_RIGHT),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=6.8, leading=9, textColor=MUTED, alignment=TA_CENTER),
    }


# ---------------------------------------------------------------- page furniture


def _zellige_band(canvas, y: float, x0: float, x1: float, color=SAFFRON, size: float = 2.3 * mm) -> None:
    """A thin ornament rule: small eight-point stars between two hairlines."""
    canvas.saveState()
    canvas.setStrokeColor(color)
    canvas.setLineWidth(0.45)
    canvas.line(x0, y + size * 0.9, x1, y + size * 0.9)
    canvas.line(x0, y - size * 0.9, x1, y - size * 0.9)
    step = size * 2.6
    x = x0 + step / 2
    while x < x1 - step / 4:
        for angle in (0, 45):
            canvas.saveState()
            canvas.translate(x, y)
            canvas.rotate(angle)
            canvas.rect(-size / 2, -size / 2, size, size, stroke=1, fill=0)
            canvas.restoreState()
        x += step
    canvas.restoreState()


def _draw_header(canvas, title_fr: str, title_ar: str) -> None:
    top = PAGE_H - 0.9 * cm
    canvas.saveState()

    # Coat of arms, centred
    coat = ensure_coat_header_image()
    coat_h = 1.75 * cm
    if coat.exists():
        canvas.drawImage(str(coat), PAGE_W / 2 - coat_h / 2, top - coat_h, width=coat_h, height=coat_h,
                         preserveAspectRatio=True, mask="auto")

    # French letterhead (left)
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 10.5)
    canvas.drawString(MARGIN_L, top - 0.45 * cm, "ROYAUME DU MAROC")
    canvas.setFont("Helvetica", 7.4)
    canvas.setFillColor(INK_2)
    canvas.drawString(MARGIN_L, top - 0.85 * cm, "Hébergement touristique")
    canvas.drawString(MARGIN_L, top - 1.2 * cm, "Location de courte durée")

    # Arabic letterhead (right)
    canvas.setFillColor(INK)
    canvas.setFont(AR_FONT_BOLD, 12)
    canvas.drawRightString(PAGE_W - MARGIN_R, top - 0.5 * cm, ar("المملكة المغربية"))
    canvas.setFont(AR_FONT, 8.4)
    canvas.setFillColor(INK_2)
    canvas.drawRightString(PAGE_W - MARGIN_R, top - 0.9 * cm, ar("الإيواء السياحي"))
    canvas.drawRightString(PAGE_W - MARGIN_R, top - 1.27 * cm, ar("الكراء قصير المدة"))

    # Ornament rule
    _zellige_band(canvas, top - 2.15 * cm, MARGIN_L, PAGE_W - MARGIN_R)
    canvas.restoreState()


def _draw_watermark(canvas) -> None:
    _, watermark = ensure_logo_assets()
    if watermark.exists():
        w = 13 * cm
        h = w * 573 / 1200
        canvas.drawImage(str(watermark), PAGE_W / 2 - w / 2, PAGE_H / 2 - h / 2 - 1 * cm, width=w, height=h, mask="auto")


def _draw_footer(canvas, page: int, total: int, ref: str, host_name: str) -> None:
    canvas.saveState()
    y = 1.25 * cm
    canvas.setStrokeColor(CLAY)
    canvas.setLineWidth(0.8)
    canvas.line(MARGIN_L, y + 0.55 * cm, PAGE_W - MARGIN_R, y + 0.55 * cm)
    logo, _ = ensure_logo_assets()
    text_x = MARGIN_L
    if logo.exists():
        w = 1.9 * cm
        canvas.drawImage(str(logo), MARGIN_L, y - 0.42 * cm, width=w, height=w * 573 / 1200, mask="auto")
        text_x = MARGIN_L + w + 0.35 * cm
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 7.2)
    canvas.drawString(text_x, y + 0.08 * cm, "Contrat de location saisonnière")
    canvas.setFont("Helvetica", 6.6)
    canvas.setFillColor(MUTED)
    host = f"Établissement : {host_name} · " if host_name else ""
    canvas.drawString(text_x, y - 0.25 * cm, f"{host}Document généré électroniquement ({settings.app_name})")
    canvas.drawRightString(PAGE_W - MARGIN_R, y + 0.08 * cm, f"Réf. {ref}")
    canvas.drawRightString(PAGE_W - MARGIN_R, y - 0.25 * cm, f"Page {page} / {total}")
    canvas.restoreState()



def _build(output_path, story: list, *, ref: str, host_name: str, title: str,
           headers: list[tuple[str, str]], total_pages: int) -> int:
    """Render `story`; returns the number of pages produced. `output_path` may be a path or a buffer."""
    _register_fonts()
    counter = [0]

    def on_page(canvas, _doc):
        counter[0] += 1
        _draw_watermark(canvas)
        fr, ar_title = headers[min(counter[0] - 1, len(headers) - 1)]
        _draw_header(canvas, fr, ar_title)
        _draw_footer(canvas, counter[0], total_pages, ref, host_name)

    doc = BaseDocTemplate(output_path if hasattr(output_path, "write") else str(output_path), pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
                          topMargin=HEADER_H, bottomMargin=FOOTER_H + 0.4 * cm, title=title, author=settings.app_name)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=on_page)])
    doc.build(story)
    return counter[0]

# ---------------------------------------------------------------- contract content

MA_TZ = ZoneInfo("Africa/Casablanca")
PLACEHOLDER_HINT = "À préciser par l'Hôte (logement non encore attribué)"

HOUSE_RULES = [
    "Respecter la capacité maximale autorisée du logement.",
    "Ne recevoir aucun visiteur ni voyageur non déclaré sans l'accord écrit préalable de l'Hôte.",
    "Respecter le voisinage et s'abstenir de toute nuisance sonore entre 22h00 et 09h00.",
    "S'interdire toute fête ou événement dans le logement.",
    "Maintenir le logement en bon état comme un bon père de famille.",
    "Signaler immédiatement à l'Hôte tout dommage ou incident.",
    "Respecter les horaires d'arrivée (check-in) et de départ (check-out) fixés par l'Hôte, et quitter le "
    "logement à l'heure prévue.",
    "Restituer les clés et équipements mis à disposition à la fin du séjour.",
    "Ne pas louer, sous-louer, prêter ni mettre le logement à la disposition d'autres personnes pendant son "
    "séjour : le Voyageur n'a aucun droit de le relouer.",
    "Conformément à la législation marocaine, tout couple dont au moins un membre est de nationalité marocaine "
    "doit présenter un acte de mariage ; les couples non mariés comprenant une personne de nationalité marocaine "
    "ne sont pas autorisés.",
    "S'interdire d'introduire, de détenir ou de consommer de l'alcool, des drogues ou toute substance illicite, "
    "ainsi que toute prostitution ou activité illégale, strictement interdites et signalées aux autorités.",
    "Respecter les lois et règlements en vigueur au Royaume du Maroc.",
]

ARTICLES = [
    ("Article 3 – Données personnelles",
     "Le Voyageur consent expressément à ce que l'Hôte recueille et conserve une copie ou une photographie de sa "
     "pièce d'identité (CIN ou passeport), aux seules fins d'enregistrement du séjour et de respect des obligations "
     "légales de déclaration de la clientèle. Ce traitement est effectué conformément à la loi n° 09-08. Le "
     "Voyageur dispose d'un droit d'accès, de rectification et d'opposition."),
]
AFTER_RULES = [
    ("Article 5 – Responsabilité",
     "Le Voyageur est responsable des dégradations, pertes et vols survenus pendant son séjour, ainsi que des "
     "agissements de ses accompagnants et visiteurs. L'Hôte décline toute responsabilité en cas de perte ou de vol "
     "d'effets personnels du Voyageur."),
    ("Article 6 – Manquement et résiliation",
     "En cas de manquement au présent règlement, l'Hôte peut résilier le contrat de plein droit et sans mise en "
     "demeure préalable. Le Voyageur doit alors quitter les lieux immédiatement."),
    ("Article 7 – Force obligatoire",
     "Conformément à l'article 230 du Dahir des obligations et des contrats (DOC), les obligations contractées "
     "valablement tiennent lieu de loi à ceux qui les ont faites. Le Voyageur reconnaît avoir lu et compris le "
     "présent contrat."),
    ("Article 8 – Droit applicable et juridiction",
     "Le présent contrat est soumis au droit marocain. À défaut de règlement amiable, tout litige relève de la "
     "compétence exclusive des tribunaux de Rabat."),
]
DECLARATION = (
    "Le Voyageur déclare avoir lu et approuvé l'ensemble des articles ci-dessus. Il signe le présent contrat par "
    "voie électronique, conformément à la loi n° 43-20 relative aux services de confiance pour les transactions "
    "électroniques (Dahir n° 1-20-100 du 31 décembre 2020) et aux dispositions du Code des obligations et des "
    "contrats (DOC) : la signature électronique produit les effets juridiques attachés à la signature manuscrite "
    "dans les conditions prévues par cette loi. La mention « Lu et approuvé » est apposée électroniquement."
)


def _fdate(value: str) -> str:
    """2026-10-15 -> 15/10/2026 (anything else is returned as is)."""
    try:
        return datetime.strptime((value or "")[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return value or "—"


def _nights(arrival: str, departure: str) -> int | None:
    try:
        a = datetime.strptime(arrival[:10], "%Y-%m-%d")
        d = datetime.strptime(departure[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return max((d - a).days, 0)


def _signed_at(submission: Submission) -> datetime:
    when = submission.submitted_at or datetime.utcnow()
    if when.tzinfo is None:
        from datetime import timezone

        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(MA_TZ)


def _city(address: str) -> str:
    parts = [p.strip() for p in (address or "").split(",") if p.strip()]
    return parts[-1] if len(parts) > 1 else ""


def _host_name(submission: Submission) -> str:
    section = getattr(submission, "section", None)
    return section.name if section else ""


def _host_lines(submission: Submission) -> list[str]:
    section = getattr(submission, "section", None)
    info = (getattr(section, "legal_info", None) or "").strip()
    return [ln.strip() for ln in info.splitlines() if ln.strip()]


def _st(f: float = 1.0) -> dict:
    """Contract text styles; every size is multiplied by f so the text can be fitted to one page."""
    s = _styles()
    s.update({
        "doc_title": ParagraphStyle("doc_title", fontName="Helvetica-Bold", fontSize=15*f, leading=18*f, textColor=CLAY, alignment=TA_CENTER),
        "doc_title_ar": ParagraphStyle("doc_title_ar", fontName=AR_FONT_BOLD, fontSize=13*f, leading=17*f, textColor=CLAY_DARK, alignment=TA_CENTER),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10.5*f, leading=13*f, textColor=CLAY, alignment=TA_CENTER, spaceBefore=3, spaceAfter=2),
        "h2l": ParagraphStyle("h2l", fontName="Helvetica-Bold", fontSize=8.6*f, leading=11*f, textColor=CLAY, spaceBefore=2.5, spaceAfter=1.5),
        "party_tag": ParagraphStyle("party_tag", fontName="Helvetica-Bold", fontSize=7.4*f, leading=9.5*f, textColor=CLAY),
        "party": ParagraphStyle("party", fontName="Helvetica", fontSize=8*f, leading=10.6*f, textColor=INK),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=7.9*f, leading=10.3*f, textColor=INK, alignment=TA_JUSTIFY),
        "rule": ParagraphStyle("rule", fontName="Helvetica", fontSize=7.9*f, leading=10.1*f, textColor=INK, alignment=TA_JUSTIFY,
                               leftIndent=13*f, firstLineIndent=-13*f),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=7.9*f, leading=10*f, textColor=INK),
        "cell_h": ParagraphStyle("cell_h", fontName="Helvetica-Bold", fontSize=7.6*f, leading=9.5*f, textColor=WHITE),
        "sig_small": ParagraphStyle("sig_small", fontName="Helvetica", fontSize=6.6*f, leading=8.4*f, textColor=INK_2),
    })
    return s


def _title_row(styles: dict) -> Table:
    logo, _ = ensure_logo_assets()
    w = 3.5 * cm
    img = Image(str(logo), width=w, height=w * 573 / 1200) if logo.exists() else ""
    center = [Paragraph("CONTRAT DE LOCATION SAISONNIÈRE", styles["doc_title"]),
              Paragraph(_escape(ar("عقد كراء موسمي")), styles["doc_title_ar"]),
              Paragraph("Hébergement touristique — Location de courte durée", styles["subtitle"])]
    t = Table([[img, center, ""]], colWidths=[w + 0.2 * cm, CONTENT_W - 2 * (w + 0.2 * cm), w + 0.2 * cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _meta(submission: Submission, signed: datetime, styles: dict) -> Table:
    ref = submission.public_id[:8].upper()
    left = Paragraph(f'<font name="Helvetica-Bold" color="#7A3319">Contrat N° {ref}</font>', styles["meta"])
    right = Paragraph(f'<font name="Helvetica-Bold" color="#7A3319">Établi le</font> '
                      f'{signed.strftime("%d/%m/%Y à %H:%M")} (heure du Maroc)', styles["meta_r"])
    t = Table([[left, right]], colWidths=[CONTENT_W * 0.4, CONTENT_W * 0.6])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SAND), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("LINEBEFORE", (0, 0), (0, 0), 2.5, CLAY),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _parties(submission: Submission, styles: dict) -> Table:
    host = _host_name(submission) or "L'Hôte"
    lines = _host_lines(submission)
    left = [Paragraph("D'UNE PART — L'HÔTE", styles["party_tag"])]
    if lines:
        left.append(Paragraph(f"<b>{_escape(lines[0])}</b>", styles["party"]))
        left += [Paragraph(_escape(ln), styles["party"]) for ln in lines[1:]]
    else:
        left += [Paragraph(f"<b>{_escape(host)}</b>", styles["party"]),
                 Paragraph("Exploitant du logement ci-dessous désigné", styles["party"])]
    name = f"{_escape(submission.first_name)} {_escape(submission.last_name).upper()}"
    right = [Paragraph("D'AUTRE PART — LE VOYAGEUR", styles["party_tag"]),
             Paragraph(f"<b>{name}</b>", styles["party"]),
             Paragraph(f"Né(e) le {_escape(_fdate(submission.date_of_birth))} · Nationalité : {_escape(submission.nationality)}", styles["party"]),
             Paragraph(f"Pays de résidence : {_escape(submission.country_of_residence)}", styles["party"]),
             Paragraph(f"{_escape(submission.id_document_type)} n° <b>{_escape(submission.id_document_number)}</b>", styles["party"])]
    half = (CONTENT_W - 4 * mm) / 2
    t = Table([[left, "", right]], colWidths=[half, 4 * mm, half])
    box = [("BOX", (0, 0), (0, 0), 0.8, CLAY), ("BOX", (2, 0), (2, 0), 0.8, CLAY),
           ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#FDF1EA")), ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#FDF1EA")),
           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
           ("LEFTPADDING", (1, 0), (1, 0), 0), ("RIGHTPADDING", (1, 0), (1, 0), 0)]
    t.setStyle(TableStyle(box))
    return t


def _travelers(submission: Submission, signature_file: Path, styles: dict, f: float = 1.0) -> Table:
    sig = (Image(str(signature_file), width=2.5 * cm, height=0.9 * cm)
           if signature_file.exists() else Paragraph("—", styles["cell"]))
    rows = [[Paragraph(h, styles["cell_h"]) for h in ("Nom et prénom", "Nationalité", "N° CIN / Passeport", "Signature")],
            [Paragraph(f"<b>{_escape(submission.last_name).upper()} {_escape(submission.first_name)}</b>", styles["cell"]),
             Paragraph(_escape(submission.nationality), styles["cell"]),
             Paragraph(_escape(submission.id_document_number), styles["cell"]), sig]]
    extra = min(max((submission.number_of_guests or 1) - 1, 0), 5)
    rows += [["", "", "", ""] for _ in range(extra)]
    widths = [CONTENT_W * 0.34, CONTENT_W * 0.2, CONTENT_W * 0.24, CONTENT_W * 0.22]
    t = Table(rows, colWidths=widths, rowHeights=[None, 1.0 * cm * f] + [0.62 * cm * f] * extra)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), CLAY), ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("BOX", (0, 0), (-1, -1), 0.7, CLAY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (3, 1), (3, 1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 3 * f), ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * f),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _signature_block(submission: Submission, signature_file: Path, signed: datetime, place_city: str, styles: dict,
                     f: float = 1.0) -> Table:
    sig = (Image(str(signature_file), width=4.4 * cm, height=1.6 * cm)
           if signature_file.exists() else Paragraph("(signature non enregistrée)", styles["sig_small"]))
    name = f"{submission.first_name} {submission.last_name}"
    left = [Paragraph('<font name="Helvetica-Bold" color="#7A3319">Signature électronique du Voyageur</font>', styles["sig_small"]),
            Paragraph("(certificat de signature électronique – loi n° 43-20)", styles["sig_small"]),
            Paragraph('<font name="Helvetica-BoldOblique">Lu et approuvé</font>', styles["sig_small"]), Spacer(1, 2), sig]
    mid = [Paragraph(f'<font name="Helvetica-Bold">Fait à :</font> {_escape(place_city) or "____________________"}', styles["cell"]),
           Spacer(1, 4),
           Paragraph(f'<font name="Helvetica-Bold">Date et heure (horodatage) :</font> {signed.strftime("%d/%m/%Y à %H:%M")}', styles["cell"]),
           Spacer(1, 4),
           Paragraph(f'<font name="Helvetica-Bold">Nom du signataire :</font> {_escape(name)}', styles["cell"]),
           Spacer(1, 4),
           Paragraph(f'<font name="Helvetica-Bold">Référence de la transaction / certificat :</font> '
                     f'{submission.public_id[:8].upper()}-{signed.strftime("%Y%m%d%H%M")}', styles["cell"])]
    right = [Paragraph('<font name="Helvetica-Bold" color="#7A3319">Cachet et signature de l\'Hôte</font>', styles["sig_small"])]
    t = Table([[left, mid, right]], colWidths=[CONTENT_W * 0.30, CONTENT_W * 0.45, CONTENT_W * 0.25], rowHeights=[3.0 * cm * f])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, CLAY), ("LINEAFTER", (0, 0), (1, 0), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#FDF1EA")),
    ]))
    return t


def _contract_story(submission: Submission, apartment_name: str, apartment_address: str,
                    signature_file: Path, f: float) -> list:
    from app.services.property_placeholder import PROPERTY_PLACEHOLDER

    styles = _st(f)
    signed = _signed_at(submission)
    assigned = apartment_name != PROPERTY_PLACEHOLDER
    place = (apartment_name if not apartment_address or apartment_address == apartment_name
             else f"{apartment_name}, {apartment_address}") if assigned else PLACEHOLDER_HINT
    nights = _nights(submission.arrival_date, submission.departure_date)
    stay = (f" ({nights} nuit{'s' if nights and nights > 1 else ''})" if nights else "")
    guests = f"{submission.number_of_guests} voyageur{'s' if submission.number_of_guests > 1 else ''}"
    if submission.number_of_kids:
        guests += f" dont {submission.number_of_kids} enfant{'s' if submission.number_of_kids > 1 else ''}"
    gap = lambda mm_: Spacer(1, mm_ * mm * f)

    def article(title: str, body: str) -> list:
        return [Paragraph(_escape(title), styles["h2l"]), Paragraph(_escape(body), styles["body"])]

    story: list = [
        _title_row(styles), gap(2.2), _meta(submission, signed, styles), gap(2.4),
        Paragraph("ENTRE LES SOUSSIGNÉS", styles["h2l"]), _parties(submission, styles), gap(1.2),
        Paragraph("CONDITIONS", styles["h2"]),
        Paragraph("Article 1 – Objet et durée", styles["h2l"]),
        Paragraph("Le présent contrat a pour objet la mise à disposition temporaire, à titre de location saisonnière, "
                  f"du logement suivant : <b>{_escape(place)}</b>. Période : "
                  f"<b>Date de check-in : {_escape(_fdate(submission.arrival_date))}</b> &nbsp;&nbsp; "
                  f"<b>Date de check-out : {_escape(_fdate(submission.departure_date))}</b>{stay} · {guests}.", styles["body"]),
        Paragraph("Article 2 – Identification des voyageurs", styles["h2l"]),
        _travelers(submission, signature_file, styles, f), gap(1.6),
        Paragraph("Le Voyageur certifie l'exactitude et l'exhaustivité des informations communiquées. Toute fausse "
                  "déclaration engage sa seule responsabilité.", styles["body"]),
    ]
    for title, body in ARTICLES:
        story += article(title, body)
    story.append(Paragraph("Article 4 – Règlement intérieur", styles["h2l"]))
    story.append(Paragraph("Le Voyageur reconnaît avoir pris connaissance du règlement intérieur du logement et "
                           "s'engage à le respecter pendant toute la durée du séjour :", styles["body"]))
    for i, rule in enumerate(HOUSE_RULES, 1):
        story.append(Paragraph(f"{i}.&nbsp; {_escape(rule)}", styles["rule"]))
    for title, body in AFTER_RULES:
        story += article(title, body)
    story += [Paragraph("Déclaration d'acceptation et signature électronique", styles["h2l"]),
              Paragraph(_escape(DECLARATION), styles["body"]), gap(2.2),
              _signature_block(submission, signature_file, signed, _city(apartment_address) if assigned else "", styles, f)]
    return story


def generate_contract_pdf(submission: Submission, apartment_name: str, apartment_address: str,
                          signature_file: Path, output_path: Path) -> None:
    """One A4 contract filled with what the guest provided (identity, stay, signature).

    The text is sized as large as possible while keeping the whole contract on a single page.
    """
    from io import BytesIO

    _register_fonts()
    kw = dict(ref=submission.public_id[:8].upper(), host_name=_host_name(submission),
              title="Contrat de location saisonnière", headers=[("CONTRAT", "")])
    f = 1.1
    while f > 0.72:
        story = _contract_story(submission, apartment_name, apartment_address, signature_file, f)
        if _build(BytesIO(), story, total_pages=1, **kw) == 1:
            break
        f -= 0.02
    story = _contract_story(submission, apartment_name, apartment_address, signature_file, f)
    pages = _build(BytesIO(), list(story), total_pages=1, **kw)
    story = _contract_story(submission, apartment_name, apartment_address, signature_file, f)
    _build(output_path, story, total_pages=pages, **kw)
