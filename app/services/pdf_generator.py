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
from reportlab.platypus import Image, KeepTogether, Paragraph, Spacer, Table, TableStyle
from reportlab.platypus.doctemplate import BaseDocTemplate, Frame, PageTemplate

from app.config import PROJECT_ROOT, get_settings
from app.models import Submission
from app.services.pdf_assets import ensure_logo_assets, logo_ratio

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
MARGIN_L = MARGIN_R = 1.35 * cm
HEADER_H = 2.55 * cm
FOOTER_H = 1.6 * cm
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


def _draw_header(canvas, ref_line: str, date_line: str) -> None:
    """Letterhead: logo on the left, contract title in the middle, contract number on the right."""
    top = PAGE_H - 0.6 * cm
    canvas.saveState()
    logo, _ = ensure_logo_assets()
    h = 1.9 * cm
    w = h / logo_ratio()
    if logo.exists():
        canvas.drawImage(str(logo), MARGIN_L - 0.1 * cm, top - h, width=w, height=h, mask="auto")
    right_w = 4.4 * cm
    mid = MARGIN_L + w + (CONTENT_W - w - right_w) / 2
    title = "CONTRAT DE LOCATION SAISONNIÈRE"
    room = CONTENT_W - w - right_w - 0.4 * cm
    size = 17.0
    while size > 11 and pdfmetrics.stringWidth(title, "Helvetica-Bold", size) > room:
        size -= 0.25
    canvas.setFillColor(CLAY)
    canvas.setFont("Helvetica-Bold", size)
    canvas.drawCentredString(mid, top - 1.2 * cm, title)
    canvas.setFillColor(INK_2)
    canvas.setFont("Helvetica", 10)
    canvas.drawRightString(PAGE_W - MARGIN_R, top - 1.25 * cm, ref_line)
    canvas.restoreState()


def _draw_watermark(canvas) -> None:
    _, watermark = ensure_logo_assets()
    if watermark.exists():
        h = 12 * cm
        w = h / logo_ratio()
        canvas.drawImage(str(watermark), PAGE_W / 2 - w / 2, PAGE_H / 2 - h / 2 - 1 * cm, width=w, height=h, mask="auto")


def _draw_footer(canvas, page: int, total: int, ref: str, host_name: str) -> None:
    canvas.saveState()
    y = 0.95 * cm
    canvas.setStrokeColor(CLAY)
    canvas.setLineWidth(0.8)
    canvas.line(MARGIN_L, y + 0.55 * cm, PAGE_W - MARGIN_R, y + 0.55 * cm)
    logo, _ = ensure_logo_assets()
    text_x = MARGIN_L
    if logo.exists():
        h = 1.0 * cm
        w = h / logo_ratio()
        canvas.drawImage(str(logo), MARGIN_L, y - 0.45 * cm, width=w, height=h, mask="auto")
        text_x = MARGIN_L + w + 0.35 * cm
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(text_x, y + 0.08 * cm, "Contrat de location saisonnière")
    canvas.setFont("Helvetica", 7.2)
    canvas.setFillColor(MUTED)
    host = f"Établissement : {host_name} · " if host_name else ""
    canvas.drawString(text_x, y - 0.25 * cm, f"{host}Document généré électroniquement ({settings.app_name})")
    canvas.drawRightString(PAGE_W - MARGIN_R, y + 0.08 * cm, f"Réf. {ref}")
    canvas.drawRightString(PAGE_W - MARGIN_R, y - 0.25 * cm, f"Page {page} / {total}")
    canvas.restoreState()



def _build(output_path, story: list, *, ref: str, host_name: str, title: str,
           meta: tuple[str, str], total_pages: int) -> int:
    """Render `story`; returns the number of pages produced. `output_path` may be a path or a buffer."""
    _register_fonts()
    counter = [0]

    def on_page(canvas, _doc):
        counter[0] += 1
        _draw_watermark(canvas)
        _draw_header(canvas, *meta)
        _draw_footer(canvas, counter[0], total_pages, ref, host_name)

    doc = BaseDocTemplate(output_path if hasattr(output_path, "write") else str(output_path), pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
                          topMargin=HEADER_H, bottomMargin=FOOTER_H + 0.15 * cm, title=title, author=settings.app_name)
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
    "Respecter le voisinage, s'abstenir de toute nuisance sonore entre 22h00 et 09h00 et s'interdire toute fête "
    "ou événement dans le logement.",
    "Maintenir le logement en bon état comme un bon père de famille et signaler immédiatement à l'Hôte tout "
    "dommage ou incident.",
    "Respecter les horaires d'arrivée (check-in) et de départ (check-out) fixés par l'Hôte, et quitter le "
    "logement à l'heure prévue.",
    "Restituer les clés et équipements mis à disposition à la fin du séjour.",
    "Ne pas louer ni sous-louer le logement, et ne pas le prêter ou le mettre à la disposition d'autres "
    "personnes pendant son séjour.",
    "Tout couple comprenant une personne de nationalité marocaine doit présenter un acte de mariage, "
    "sinon il n'est pas autorisé.",
    "L'alcool, les drogues, les substances illicites, la prostitution et toute activité illégale sont "
    "strictement interdits et seront signalés aux autorités.",
    "Respecter les lois et règlements en vigueur au Royaume du Maroc.",
]

ARTICLES = [
    ("Article 3 – Données personnelles",
     "Le Voyageur consent à ce que l'Hôte recueille et conserve une copie ou une photographie de sa pièce "
     "d'identité (CIN ou passeport). Ces données servent uniquement à l'enregistrement du séjour et au respect "
     "des obligations de déclaration de la clientèle."),
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
     "contrat."),
    ("Article 8 – Droit applicable et juridiction",
     "Le contrat est soumis au droit marocain et tout litige non réglé à l'amiable relève de la "
     "compétence exclusive des tribunaux de Rabat."),
]
DECLARATION = (
    "Le Voyageur déclare avoir lu et approuvé l'ensemble des articles ci-dessus. Il signe le présent contrat par "
    "voie électronique, conformément au Dahir n° 1-20-100 du 31 décembre 2020, la mention « Lu et approuvé » "
    "étant apposée électroniquement."
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


def _host_address(submission: Submission) -> str:
    section = getattr(submission, "section", None)
    return (getattr(section, "address", None) or "").strip()


def _host_lines(submission: Submission) -> list[str]:
    section = getattr(submission, "section", None)
    info = (getattr(section, "legal_info", None) or "").strip()
    return [ln.strip() for ln in info.splitlines() if ln.strip()]


def _st(f: float = 1.0) -> dict:
    """Contract text styles (10 pt body at f = 1); every size is multiplied by f so the text fits the page."""
    s = _styles()
    s.update({
        "party_tag": ParagraphStyle("party_tag", fontName="Helvetica-Bold", fontSize=8.6 * f, leading=11 * f, textColor=CLAY),
        "party": ParagraphStyle("party", fontName="Helvetica", fontSize=10 * f, leading=12.6 * f, textColor=INK),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10 * f, leading=12.5 * f, textColor=INK,
                               alignment=TA_JUSTIFY, spaceBefore=2.4 * f),
        "h2l": ParagraphStyle("h2l", fontName="Helvetica-Bold", fontSize=10.4 * f, leading=13 * f, textColor=CLAY,
                              spaceBefore=4 * f, spaceAfter=1 * f, keepWithNext=1),
        "rule": ParagraphStyle("rule", fontName="Helvetica", fontSize=10 * f, leading=12.3 * f, textColor=INK,
                               alignment=TA_JUSTIFY, leftIndent=16 * f, firstLineIndent=-16 * f),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=10 * f, leading=12 * f, textColor=INK),
        "sig_small": ParagraphStyle("sig_small", fontName="Helvetica", fontSize=8.4 * f, leading=10.6 * f, textColor=INK_2),
    })
    return s


def _parties(submission: Submission, styles: dict) -> Table:
    host = _host_name(submission) or "L'Hôte"
    lines = _host_lines(submission)
    left = [Paragraph("D'UNE PART — L'HÔTE", styles["party_tag"])]
    address = _host_address(submission)
    left.append(Paragraph(f"<b>{_escape(lines[0] if lines else host)}</b>", styles["party"]))
    if address:
        left.append(Paragraph(_escape(address), styles["party"]))
    left += [Paragraph(_escape(ln), styles["party"]) for ln in lines[1:]]
    if not lines and not address:
        left.append(Paragraph("Exploitant du logement ci-dessous désigné", styles["party"]))
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


def _signature_block(submission: Submission, signature_file: Path, signed: datetime, place_city: str, styles: dict,
                     f: float = 1.0) -> Table:
    sig = (Image(str(signature_file), width=3.8 * cm * f, height=1.35 * cm * f)
           if signature_file.exists() else Paragraph("(signature non enregistrée)", styles["sig_small"]))
    name = f"{submission.first_name} {submission.last_name}"
    left = [Paragraph('<font name="Helvetica-Bold" color="#7A3319">Signature électronique du Voyageur</font>', styles["sig_small"]),
            Paragraph("(certificat de signature électronique)", styles["sig_small"]),
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
    t = Table([[left, mid, right]], colWidths=[CONTENT_W * 0.29, CONTENT_W * 0.51, CONTENT_W * 0.20], rowHeights=[None])
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

    def runin(title: str, body: str, raw: bool = False) -> Paragraph:
        """Article title in bold on the same line as its text."""
        text = body if raw else _escape(body)
        return Paragraph(f'<font name="Helvetica-Bold" color="#B8532D">{_escape(title)}.</font> {text}', styles["body"])

    story: list = [
        Paragraph("ENTRE LES SOUSSIGNÉS", styles["h2l"]), _parties(submission, styles),
        runin("Article 1 – Objet et durée",
              "Le présent contrat a pour objet la mise à disposition temporaire, à titre de location saisonnière, "
              f"du logement suivant : <b>{_escape(place)}</b>. Période : "
              f"<b>check-in le {_escape(_fdate(submission.arrival_date))}</b>, "
              f"<b>check-out le {_escape(_fdate(submission.departure_date))}</b>{stay} · {guests}.", raw=True),
        runin("Article 2 – Identification et responsabilité du Voyageur",
              "Le Voyageur certifie l'exactitude et l'exhaustivité des informations communiquées ; toute fausse "
              "déclaration engage sa seule responsabilité. La personne ayant loué le logement (identifiée ci-dessus) "
              "est responsable de toutes les personnes qui l'accompagnent dans le logement et leur fait respecter le "
              "règlement intérieur."),
    ]
    for title, body in ARTICLES:
        story.append(runin(title, body))
    story.append(runin("Article 4 – Règlement intérieur",
                       "Le Voyageur a pris connaissance du règlement intérieur du logement et s'engage à le "
                       "respecter pendant tout son séjour&nbsp;:", raw=True))
    for i, rule in enumerate(HOUSE_RULES, 1):
        story.append(Paragraph(f"{i}.&nbsp; {_escape(rule)}", styles["rule"]))
    for title, body in AFTER_RULES:
        story.append(runin(title, body))
    story += [KeepTogether([runin("Déclaration d'acceptation et signature électronique", DECLARATION), Spacer(1, 3 * mm * f),
                            _signature_block(submission, signature_file, signed, _city(_host_address(submission)) or (_city(apartment_address) if assigned else ""), styles, f)])]
    return story


def generate_contract_pdf(submission: Submission, apartment_name: str, apartment_address: str,
                          signature_file: Path, output_path: Path) -> None:
    """The contract filled with what the guest provided (identity, stay, signature), on one A4 page.

    The text is sized as large as possible while the whole contract still fits on the page.
    """
    from io import BytesIO

    _register_fonts()
    signed = _signed_at(submission)
    kw = dict(ref=submission.public_id[:8].upper(), host_name=_host_name(submission),
              title="Contrat de location saisonnière", total_pages=1,
              meta=(f"N° {submission.public_id[:8].upper()}", ""))

    def story(f):
        return _contract_story(submission, apartment_name, apartment_address, signature_file, f)

    f = 1.0  # 10 pt body text; shrinks only if a very long contract would not fit on the page
    while f > 0.6 and _build(BytesIO(), story(f), **kw) > 1:
        f -= 0.01
    _build(output_path, story(f), **kw)
