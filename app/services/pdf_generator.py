"""Legal A4 PDFs — Fiche de police + Règlement signé (FR page + EN page)."""

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.doctemplate import BaseDocTemplate, Frame, PageTemplate

from app.config import get_settings
from app.models import Submission
from app.services.pdf_assets import ensure_coat_header_image

settings = get_settings()

MOROCCO_GREEN = colors.HexColor("#006233")
MOROCCO_RED = colors.HexColor("#C1272D")
GOLD = colors.HexColor("#C5A028")
BORDER = colors.HexColor("#c5d0c8")
TEXT_MUTED = colors.HexColor("#4a5c55")
TEXT_DARK = colors.HexColor("#1a2332")
BG_SECTION = colors.HexColor("#f4f7f5")
BG_ROW_ALT = colors.HexColor("#fafcfb")
SECTION_HEADER_BG = colors.HexColor("#e6f0ea")
WHITE = colors.white
RULES_TOP_GAP = 10 * mm
RULES_AFTER_TITLE_GAP = 8 * mm

PAGE_W, PAGE_H = A4
MARGIN_L = 1.75 * cm
MARGIN_R = 1.75 * cm
HEADER_H = 2.25 * cm
FOOTER_H = 2.15 * cm
SECTION_GAP = 3 * mm
BLOCK_GAP = 4 * mm
CELL_PAD_H = 10
CELL_PAD_V = 6


def _escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace("\n", " ")


def _styles():
    return {
        "meta": ParagraphStyle(
            "Meta",
            fontName="Helvetica",
            fontSize=8,
            textColor=TEXT_MUTED,
            leading=11,
            spaceAfter=2,
        ),
        "meta_bold": ParagraphStyle(
            "MetaBold",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=MOROCCO_GREEN,
            leading=11,
        ),
        "section_header": ParagraphStyle(
            "SectionHeader",
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=MOROCCO_GREEN,
            leading=12,
            spaceBefore=0,
            spaceAfter=2,
        ),
        "label": ParagraphStyle(
            "Label",
            fontName="Helvetica",
            fontSize=8,
            textColor=TEXT_MUTED,
            leading=11,
        ),
        "value": ParagraphStyle(
            "Value",
            fontName="Helvetica-Bold",
            fontSize=8.5,
            textColor=TEXT_DARK,
            leading=11,
        ),
        "rules_doc_title": ParagraphStyle(
            "RulesDocTitle",
            fontName="Helvetica-Bold",
            fontSize=9.5,
            textColor=MOROCCO_GREEN,
            leading=12,
            spaceBefore=0,
            spaceAfter=0,
            alignment=TA_CENTER,
        ),
        "rules_article_title": ParagraphStyle(
            "RulesArticleTitle",
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=TEXT_DARK,
            leading=11,
            spaceBefore=5,
            spaceAfter=2,
        ),
        "rules_article_body": ParagraphStyle(
            "RulesArticleBody",
            fontName="Helvetica",
            fontSize=7.5,
            leading=10.5,
            textColor=TEXT_DARK,
            alignment=TA_JUSTIFY,
            spaceAfter=3,
        ),
        "legal_notice": ParagraphStyle(
            "LegalNotice",
            fontName="Helvetica-Oblique",
            fontSize=7.5,
            textColor=TEXT_MUTED,
            alignment=TA_JUSTIFY,
            leading=10.5,
        ),
        "legal_notice_center": ParagraphStyle(
            "LegalNoticeCenter",
            fontName="Helvetica-Oblique",
            fontSize=7.5,
            textColor=TEXT_MUTED,
            alignment=TA_CENTER,
            leading=10.5,
            spaceBefore=2,
            spaceAfter=2,
        ),
    }


def _coat_size_in_header() -> tuple[float, float]:
    try:
        from PIL import Image as PILImage

        path = ensure_coat_header_image()
        if not path.exists():
            return 1.5 * cm, 1.5 * cm
        with PILImage.open(path) as im:
            w, h = im.size
        max_h = HEADER_H - 0.35 * cm
        ratio = w / h if h else 1
        return max_h * ratio, max_h
    except Exception:
        return 1.5 * cm, 1.5 * cm


def _draw_header(canvas, title_fr: str, title_en: str) -> None:
    """Full-width green band with coat of arms — fits A4 edge to edge."""
    coat_path = ensure_coat_header_image()
    top = PAGE_H
    bottom = top - HEADER_H

    canvas.saveState()
    canvas.setFillColor(MOROCCO_GREEN)
    canvas.rect(0, bottom, PAGE_W, HEADER_H, fill=1, stroke=0)

    stripe = 0.9 * mm
    canvas.setFillColor(GOLD)
    canvas.rect(0, bottom, PAGE_W, stripe, fill=1, stroke=0)
    canvas.setFillColor(MOROCCO_RED)
    canvas.rect(0, bottom + stripe, PAGE_W, stripe, fill=1, stroke=0)
    canvas.setFillColor(GOLD)
    canvas.rect(0, bottom + 2 * stripe, PAGE_W, stripe, fill=1, stroke=0)

    coat_w, coat_h = _coat_size_in_header()
    coat_x = 0.35 * cm
    coat_y = bottom + (HEADER_H - coat_h) / 2 + stripe * 2
    if coat_path.exists():
        try:
            reader = ImageReader(str(coat_path.resolve()))
            canvas.drawImage(reader, coat_x, coat_y, width=coat_w, height=coat_h, preserveAspectRatio=True, mask="auto")
        except Exception:
            canvas.drawImage(str(coat_path.resolve()), coat_x, coat_y, width=coat_w, height=coat_h, preserveAspectRatio=True)

    text_x = coat_x + coat_w + 0.35 * cm
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(text_x, bottom + HEADER_H * 0.52, "ROYAUME DU MAROC")
    canvas.setFont("Helvetica", 7)
    canvas.drawString(text_x, bottom + HEADER_H * 0.28, "Kingdom of Morocco")

    canvas.setFont("Helvetica-Bold", 10)
    tw = canvas.stringWidth(title_fr, "Helvetica-Bold", 10)
    canvas.drawString(PAGE_W - MARGIN_R - tw, bottom + HEADER_H * 0.52, title_fr)
    canvas.setFont("Helvetica", 7)
    tw2 = canvas.stringWidth(title_en, "Helvetica", 7)
    canvas.drawString(PAGE_W - MARGIN_R - tw2, bottom + HEADER_H * 0.28, title_en)

    canvas.restoreState()


def _draw_page_footer(canvas, page_num: int, ref_short: str, page_total: int | None = None) -> None:
    canvas.saveState()
    y_line = FOOTER_H + 0.35 * cm
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.35)
    canvas.line(MARGIN_L, y_line, PAGE_W - MARGIN_R, y_line)
    canvas.setFont("Helvetica", 6)
    canvas.setFillColor(TEXT_MUTED)
    canvas.drawCentredString(
        PAGE_W / 2,
        1.35 * cm,
        "Document établi conformément à la réglementation marocaine sur l'hébergement des voyageurs.",
    )
    canvas.drawCentredString(
        PAGE_W / 2,
        1.05 * cm,
        f"{settings.app_name} — Document généré électroniquement",
    )
    canvas.setFont("Helvetica", 6.5)
    canvas.drawString(MARGIN_L, 0.75 * cm, f"Réf. {ref_short}")
    label = f"Page {page_num}/{page_total}" if page_total else f"Page {page_num}"
    canvas.drawRightString(PAGE_W - MARGIN_R, 0.75 * cm, label)
    canvas.restoreState()


def _section_table(title: str, rows: list[tuple[str, str]], styles: dict, width: float) -> Table:
    data = [[Paragraph(title, styles["section_header"]), ""]]
    for label, value in rows:
        data.append([Paragraph(label, styles["label"]), Paragraph(_escape(value), styles["value"])])
    # Full content width — same as meta row and signature block
    label_w = width * 0.40
    value_w = width * 0.60
    t = Table(data, colWidths=[label_w, value_w])
    n = len(data)
    cmds = [
        ("SPAN", (0, 0), (1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6f0ea")),
        ("LINELEFT", (0, 0), (0, 0), 3, MOROCCO_GREEN),
        ("TOPPADDING", (0, 0), (-1, 0), CELL_PAD_V + 2),
        ("BOTTOMPADDING", (0, 0), (-1, 0), CELL_PAD_V + 2),
        ("LEFTPADDING", (0, 0), (-1, -1), CELL_PAD_H),
        ("RIGHTPADDING", (0, 0), (-1, -1), CELL_PAD_H),
        ("TOPPADDING", (0, 1), (-1, -1), CELL_PAD_V),
        ("BOTTOMPADDING", (0, 1), (-1, -1), CELL_PAD_V),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
    ]
    for r in range(1, n):
        cmds.append(("BACKGROUND", (0, r), (-1, r), BG_ROW_ALT if r % 2 == 0 else colors.white))
        if r < n - 1:
            cmds.append(("LINEBELOW", (0, r), (-1, r), 0.2, BORDER))
    t.setStyle(TableStyle(cmds))
    return t


def _meta_row(submission: Submission, submitted_at: datetime, styles: dict, width: float) -> Table:
    ref = submission.public_id[:8].upper()
    date_str = submitted_at.strftime("%d/%m/%Y à %H:%M")
    left = Paragraph(
        f'<font name="Helvetica-Bold" color="#006233">Fiche n° {ref}</font><br/>'
        f'<font size="7" color="#4a5c55">Réf. complète : {submission.public_id}</font>',
        styles["meta_bold"],
    )
    right = Paragraph(
        f'<font name="Helvetica-Bold" color="#006233">Date d\'enregistrement</font><br/>{date_str} UTC',
        styles["meta"],
    )
    t = Table([[left, right]], colWidths=[width * 0.58, width * 0.42])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BG_SECTION),
                ("BOX", (0, 0), (-1, -1), 0.6, MOROCCO_GREEN),
                ("TOPPADDING", (0, 0), (-1, -1), CELL_PAD_V + 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), CELL_PAD_V + 4),
                ("LEFTPADDING", (0, 0), (-1, -1), CELL_PAD_H + 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), CELL_PAD_H + 2),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ]
        )
    )
    return t


def _signature_block(signature_file: Path, styles: dict, width: float, label: str) -> Table:
    sig_w, sig_h = 5 * cm, 1.85 * cm
    if signature_file.exists():
        inner = Table([[Image(str(signature_file), width=sig_w, height=sig_h)]], colWidths=[width - 16 * mm])
        inner.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    else:
        inner = Table([[Paragraph("(signature non enregistrée)", styles["label"])]])
    title = Paragraph(label, styles["section_header"])
    outer = Table([[title], [inner]], colWidths=[width])
    outer.setStyle(TableStyle(_framed_block_style()))
    return outer


def _framed_block_style() -> list:
    """Shared frame style for signature block and rules guest-info block."""
    return [
        ("BACKGROUND", (0, 0), (-1, 0), SECTION_HEADER_BG),
        ("LINELEFT", (0, 0), (0, 0), 3, MOROCCO_GREEN),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (0, 0), CELL_PAD_V + 2),
        ("BOTTOMPADDING", (0, 0), (0, 0), CELL_PAD_V),
        ("TOPPADDING", (0, 1), (-1, 1), CELL_PAD_V + 4),
        ("BOTTOMPADDING", (0, 1), (-1, 1), CELL_PAD_V + 4),
        ("LEFTPADDING", (0, 0), (-1, -1), CELL_PAD_H),
        ("RIGHTPADDING", (0, 0), (-1, -1), CELL_PAD_H),
    ]


def _guest_info_table(
    submission: Submission,
    apartment_name: str,
    apartment_address: str,
    date_str: str,
    ref: str,
    styles: dict,
    width: float,
) -> Table:
    """Guest details — same framed style and colours as the signature block."""
    guest = f"{_escape(submission.first_name)} {_escape(submission.last_name)}"
    label_w = width * 0.40
    value_w = width * 0.60
    establishment = _escape(apartment_name)
    addr = (apartment_address or "").strip()
    if addr and addr != apartment_name:
        establishment = f"{establishment}, {_escape(addr)}"
    rows = [
        [Paragraph("Établissement", styles["label"]), Paragraph(establishment, styles["value"])],
        [Paragraph("Voyageur", styles["label"]), Paragraph(guest, styles["value"])],
        [
            Paragraph("Date du séjour / enregistrement", styles["label"]),
            Paragraph(f"{date_str} — Réf. {ref}", styles["value"]),
        ],
    ]
    inner = Table(rows, colWidths=[label_w, value_w])
    n = len(rows)
    inner_cmds = [
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), CELL_PAD_V + 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), CELL_PAD_V + 2),
        ("LEFTPADDING", (0, 0), (-1, -1), CELL_PAD_H),
        ("RIGHTPADDING", (0, 0), (-1, -1), CELL_PAD_H),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for r in range(n - 1):
        inner_cmds.append(("LINEBELOW", (0, r), (-1, r), 0.25, BORDER))
    inner.setStyle(TableStyle(inner_cmds))

    title = Paragraph("RENSEIGNEMENTS DU SÉJOUR", styles["section_header"])
    outer = Table([[title], [inner]], colWidths=[width])
    outer.setStyle(TableStyle(_framed_block_style()))
    return outer


def _rules_doc_title(rules_text: str) -> str | None:
    for raw in rules_text.strip().split("\n"):
        line = raw.strip()
        if line and ("RÈGLEMENT" in line or "INTERNAL RULES" in line):
            return line
    return None


def _rules_articles_flowables(rules_text: str, styles: dict, *, include_doc_title: bool = True) -> list:
    """One block per article — airy layout instead of a single dense paragraph."""
    flowables: list = []
    doc_title: str | None = None
    article_title: str | None = None
    body_lines: list[str] = []

    def flush_article() -> None:
        nonlocal article_title, body_lines
        if article_title:
            flowables.append(Paragraph(_escape(article_title), styles["rules_article_title"]))
        if body_lines:
            body = " ".join(body_lines)
            flowables.append(Paragraph(_escape(body), styles["rules_article_body"]))
        article_title = None
        body_lines = []

    for raw in rules_text.strip().split("\n"):
        line = raw.strip()
        if not line:
            continue
        is_doc_title = "RÈGLEMENT" in line or "INTERNAL RULES" in line
        is_article = len(line) >= 2 and line[0].isdigit() and line[1] in ".)"

        if is_doc_title:
            flush_article()
            doc_title = line
            continue
        if is_article:
            flush_article()
            article_title = line
            continue
        body_lines.append(line)

    flush_article()
    if doc_title and include_doc_title:
        flowables.insert(0, Paragraph(_escape(doc_title), styles["rules_doc_title"]))
    return flowables


def _attestation_box(text: str, styles: dict, width: float) -> Table:
    inner = Paragraph(text, styles["legal_notice"])
    t = Table([[inner]], colWidths=[width])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fafcfb")),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("LINELEFT", (0, 0), (0, 0), 3, MOROCCO_GREEN),
                ("TOPPADDING", (0, 0), (-1, -1), CELL_PAD_V + 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), CELL_PAD_V + 6),
                ("LEFTPADDING", (0, 0), (-1, -1), CELL_PAD_H + 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), CELL_PAD_H + 4),
            ]
        )
    )
    return t


def _build_doc(
    output_path: Path,
    story: list,
    ref_short: str,
    doc_title: str,
    header_pages: list[tuple[str, str]],
    page_total: int | None = None,
) -> None:
    page_counter = [0]
    top_margin = HEADER_H + 5 * mm

    def on_page_end(canvas, _doc):
        page_counter[0] += 1
        idx = min(page_counter[0] - 1, len(header_pages) - 1)
        title_fr, title_en = header_pages[idx]
        _draw_header(canvas, title_fr, title_en)
        total = page_total or page_counter[0]
        _draw_page_footer(canvas, page_counter[0], ref_short, page_total=total if page_total else None)

    doc = BaseDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=MARGIN_L,
        rightMargin=MARGIN_R,
        topMargin=top_margin,
        bottomMargin=FOOTER_H,
        title=doc_title,
        author=settings.app_name,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="Main", frames=[frame], onPageEnd=on_page_end)])
    doc.build(story)


def generate_fiche_pdf(
    submission: Submission,
    property_address: str,
    apartment_name: str,
    signature_file: Path,
    output_path: Path,
) -> None:
    styles = _styles()
    submitted_at = submission.submitted_at
    if submitted_at.tzinfo:
        submitted_at = submitted_at.replace(tzinfo=None)

    ref_short = submission.public_id[:8].upper()
    w = PAGE_W - MARGIN_L - MARGIN_R
    headers = [("FICHE DE POLICE", "Enregistrement voyageurs — location courte durée")]

    story = [
        _meta_row(submission, submitted_at, styles, w),
        Spacer(1, 3 * mm),
        _section_table(
            "I — HÉBERGEMENT",
            [
                ("Établissement", apartment_name),
                ("Adresse complète", property_address),
            ],
            styles,
            w,
        ),
        Spacer(1, SECTION_GAP),
        _section_table(
            "II — IDENTITÉ DU VOYAGEUR",
            [
                ("Nom de famille", submission.last_name),
                ("Prénom(s)", submission.first_name),
                ("Nationalité", submission.nationality),
                ("Date de naissance", submission.date_of_birth),
                ("Pays de résidence", submission.country_of_residence),
            ],
            styles,
            w,
        ),
        Spacer(1, SECTION_GAP),
        _section_table(
            "III — SÉJOUR ET PIÈCE D'IDENTITÉ",
            [
                ("Date d'arrivée", submission.arrival_date),
                ("Date de départ", submission.departure_date),
                ("Nombre de voyageurs", str(submission.number_of_guests)),
                ("Enfants", str(submission.number_of_kids)),
                ("Type de document", submission.id_document_type),
                ("Numéro du document", submission.id_document_number),
            ],
            styles,
            w,
        ),
        Spacer(1, SECTION_GAP),
        _section_table(
            "IV — DÉCLARATIONS",
            [
                (
                    "Règlement intérieur",
                    "✓ Lu et accepté" if submission.accept_internal_rules else "—",
                ),
                (
                    "Conditions générales",
                    "✓ Lu et accepté" if submission.accept_terms else "—",
                ),
            ],
            styles,
            w,
        ),
        Spacer(1, 3 * mm),
        _signature_block(signature_file, styles, w, "V — SIGNATURE DU VOYAGEUR"),
        Spacer(1, 2 * mm),
        Paragraph(
            "Le soussigné(e) certifie l'exactitude des renseignements ci-dessus et accepte les obligations "
            "légales en vigueur au Royaume du Maroc relatives à l'hébergement des voyageurs.",
            styles["legal_notice_center"],
        ),
    ]

    _build_doc(output_path, story, ref_short, "FICHE DE POLICE", headers, page_total=1)


def _rules_page(
    submission: Submission,
    apartment_name: str,
    apartment_address: str,
    date_str: str,
    ref_short: str,
    rules_text: str,
    attestation: str,
    signature_label: str,
    signature_file: Path,
    styles: dict,
    w: float,
) -> list:
    story = [Spacer(1, RULES_TOP_GAP)]
    doc_title = _rules_doc_title(rules_text)
    if doc_title:
        story.append(Paragraph(_escape(doc_title), styles["rules_doc_title"]))
        story.append(Spacer(1, RULES_AFTER_TITLE_GAP))
    story.append(
        _guest_info_table(submission, apartment_name, apartment_address, date_str, ref_short, styles, w)
    )
    story.append(Spacer(1, BLOCK_GAP))
    story.extend(_rules_articles_flowables(rules_text, styles, include_doc_title=False))
    story.extend(
        [
            Spacer(1, BLOCK_GAP),
            _attestation_box(attestation, styles, w),
            Spacer(1, BLOCK_GAP),
            _signature_block(signature_file, styles, w, signature_label),
        ]
    )
    return story


def generate_rules_pdf(
    submission: Submission,
    apartment_name: str,
    apartment_address: str,
    signature_file: Path,
    output_path: Path,
) -> None:
    styles = _styles()
    w = PAGE_W - MARGIN_L - MARGIN_R
    submitted_at = submission.submitted_at
    if submitted_at and submitted_at.tzinfo:
        submitted_at = submitted_at.replace(tzinfo=None)
    date_str = submitted_at.strftime("%d/%m/%Y") if submitted_at else "—"
    ref_short = submission.public_id[:8].upper()

    headers = [
        ("RÈGLEMENT INTÉRIEUR", "Résidence de courte durée — version française"),
        ("INTERNAL RULES", "Short-term rental — English version"),
    ]

    story = _rules_page(
        submission,
        apartment_name,
        apartment_address,
        date_str,
        ref_short,
        settings.load_rules_fr(),
        "Je soussigné(e), <b>"
        + _escape(submission.first_name)
        + " "
        + _escape(submission.last_name)
        + "</b>, déclare avoir pris connaissance de l'intégralité du présent règlement et m'engage à le "
        "respecter pendant toute la durée du séjour, sous peine de résiliation du contrat et de poursuites "
        "conformément à la loi marocaine en vigueur.",
        "SIGNATURE DU VOYAGEUR",
        signature_file,
        styles,
        w,
    )
    story.append(PageBreak())
    story.extend(
        _rules_page(
            submission,
            apartment_name,
            apartment_address,
            date_str,
            ref_short,
            settings.load_rules_en(),
            "I, the undersigned, <b>"
            + _escape(submission.first_name)
            + " "
            + _escape(submission.last_name)
            + "</b>, declare that I have read the entire rules above and agree to comply with them "
            "throughout my stay, failing which the rental agreement may be terminated and legal action "
            "taken under applicable Moroccan law.",
            "GUEST SIGNATURE",
            signature_file,
            styles,
            w,
        )
    )

    _build_doc(output_path, story, ref_short, "RÈGLEMENT INTÉRIEUR", headers, page_total=2)
