"""A4 PDFs in the style of a Moroccan administrative form (bilingual French / Arabic):
Fiche de police (1 page) and Règlement intérieur signé (French, English and Arabic pages).

Layout: "Royaume du Maroc" letterhead (French left, Arabic right, coat of arms centred), a zellige
ornament rule, bilingual field labels, the platform palette (terracotta / zellige green / saffron),
the company logo as a light watermark and in the footer, and a stamp box for the host.
"""

import re
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, KeepInFrame, PageBreak, Paragraph, Spacer, Table, TableStyle
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


def _ar_lines(text: str, font: str, size: float, width: float) -> list[str]:
    """Wrap Arabic text into lines that fit `width` (logical order), then put each line in visual order."""
    words, lines, current = text.split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if pdfmetrics.stringWidth(ar(trial), font, size) <= width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return [ar(line) for line in lines]


_LATIN_RUN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’.\- ]*[A-Za-zÀ-ÖØ-öø-ÿ.]|[A-Za-zÀ-ÖØ-öø-ÿ]")


def _mixed(line: str) -> str:
    """Paragraph markup for a visual Arabic line: Latin words (names…) use a Latin font."""
    def arabic_part(text: str) -> str:
        return _escape(text).replace("-", '<font name="Helvetica">-</font>')

    out, pos = [], 0
    for m in _LATIN_RUN.finditer(line):
        out.append(arabic_part(line[pos:m.start()]))
        out.append(f'<font name="Helvetica">{_escape(m.group(0))}</font>')
        pos = m.end()
    out.append(arabic_part(line[pos:]))
    return "".join(out)


def _ar_paragraphs(text: str, style: ParagraphStyle, width: float) -> list:
    text = text.replace("—", "-").replace("–", "-")  # the Arabic font has no long dashes
    return [Paragraph(_mixed(line), style) for line in _ar_lines(text, style.fontName, style.fontSize, width)]


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
        size = 11 * cm
        canvas.drawImage(str(watermark), PAGE_W / 2 - size / 2, PAGE_H / 2 - size / 2 - 1 * cm,
                         width=size, height=size, mask="auto")


def _draw_footer(canvas, page: int, total: int, ref: str, host_name: str) -> None:
    canvas.saveState()
    y = 1.25 * cm
    canvas.setStrokeColor(CLAY)
    canvas.setLineWidth(0.8)
    canvas.line(MARGIN_L, y + 0.55 * cm, PAGE_W - MARGIN_R, y + 0.55 * cm)
    logo, _ = ensure_logo_assets()
    if logo.exists():
        canvas.drawImage(str(logo), MARGIN_L, y - 0.38 * cm, width=0.8 * cm, height=0.8 * cm, mask="auto")
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 7.2)
    canvas.drawString(MARGIN_L + 1 * cm, y + 0.08 * cm, settings.app_name)
    canvas.setFont("Helvetica", 6.6)
    canvas.setFillColor(MUTED)
    host = f"Établissement : {host_name} · " if host_name else ""
    canvas.drawString(MARGIN_L + 1 * cm, y - 0.25 * cm, f"{host}Document généré électroniquement")
    canvas.drawRightString(PAGE_W - MARGIN_R, y + 0.08 * cm, f"Réf. {ref}")
    canvas.drawRightString(PAGE_W - MARGIN_R, y - 0.25 * cm, f"Page {page} / {total}")
    canvas.restoreState()


# ---------------------------------------------------------------- blocks


def _title_block(title_fr: str, title_ar: str, subtitle: str, styles: dict) -> Table:
    t = Table(
        [[Paragraph(_escape(title_fr), styles["title"])],
         [Paragraph(_escape(ar(title_ar)), styles["title_ar"])],
         [Paragraph(_escape(subtitle), styles["subtitle"])]],
        colWidths=[CONTENT_W],
    )
    t.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 2), (-1, 2), 6),
    ]))
    return t


def _meta_row(submission: Submission, submitted_at: datetime, styles: dict) -> Table:
    ref = submission.public_id[:8].upper()
    left = Paragraph(
        f'<font name="Helvetica-Bold" color="#7A3319">N° {ref}</font>'
        f'<br/><font size="6.6" color="#8A776A">{submission.public_id}</font>', styles["meta"])
    right = Paragraph(
        f'<font name="Helvetica-Bold" color="#7A3319">Enregistré le</font> '
        f'{submitted_at.strftime("%d/%m/%Y à %H:%M")} UTC<br/>'
        f'<font name="{AR_FONT}" size="7.6">{_escape(ar("تاريخ التسجيل"))}</font>', styles["meta_r"])
    t = Table([[left, right]], colWidths=[CONTENT_W * 0.5, CONTENT_W * 0.5])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SAND),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("LINEBEFORE", (0, 0), (0, 0), 2.5, CLAY),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _section(num: str, title_fr: str, title_ar: str, rows: list[tuple[str, str, str]], styles: dict) -> Table:
    """Bilingual form section: French label | value | Arabic label."""
    lw, aw = CONTENT_W * 0.30, CONTENT_W * 0.25
    vw = CONTENT_W - lw - aw
    heading = f"{num} — {_escape(title_fr)}" if num else _escape(title_fr)
    data = [[Paragraph(heading, styles["section"]), "",
             Paragraph(_escape(ar(title_ar)), styles["section_ar"])]]
    for fr_label, value, ar_label in rows:
        data.append([Paragraph(_escape(fr_label), styles["label"]),
                     Paragraph(_escape(value or "—"), styles["value"]),
                     Paragraph(_escape(ar(ar_label)), styles["label_ar"])])
    t = Table(data, colWidths=[lw, vw, aw])
    cmds = [
        ("SPAN", (0, 0), (1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), SAND_2),
        ("LINEBELOW", (0, 0), (-1, 0), 0.9, CLAY),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
    ]
    for r in range(1, len(data)):
        if r < len(data) - 1:
            cmds.append(("LINEBELOW", (0, r), (-1, r), 0.25, LINE))
        cmds.append(("BACKGROUND", (0, r), (-1, r), WHITE if r % 2 else SAND))
    t.setStyle(TableStyle(cmds))
    return t


def _signatures(signature_file: Path, styles: dict, guest_fr: str, guest_ar: str,
                stamp_label: str = "Cachet de l'établissement") -> Table:
    """Guest signature (image) next to an empty box for the host's stamp and signature."""
    half = (CONTENT_W - 6 * mm) / 2
    sig = (Image(str(signature_file), width=4.6 * cm, height=1.7 * cm)
           if signature_file.exists() else Paragraph("(signature non enregistrée)", styles["label"]))

    def box(title_fr, title_ar, body):
        b = Table([[Paragraph(_escape(title_fr), styles["section"]), Paragraph(_escape(ar(title_ar)), styles["section_ar"])],
                   [body, ""]], colWidths=[half * 0.55, half * 0.45], rowHeights=[None, 1.9 * cm])
        b.setStyle(TableStyle([
            ("SPAN", (0, 1), (1, 1)),
            ("BACKGROUND", (0, 0), (-1, 0), SAND_2),
            ("LINEBELOW", (0, 0), (-1, 0), 0.9, CLAY),
            ("BOX", (0, 0), (-1, -1), 0.6, LINE),
            ("ALIGN", (0, 1), (-1, 1), "CENTER"), ("VALIGN", (0, 1), (-1, 1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        return b

    stamp = Paragraph("", styles["label"])
    outer = Table([[box(guest_fr, guest_ar, sig), "", box(stamp_label, "خاتم المؤسسة", stamp)]],
                  colWidths=[half, 6 * mm, half])
    outer.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return outer


def _notice(text_fr: str, text_ar: str, styles: dict) -> Table:
    body = [Paragraph(text_fr, styles["notice"]), Spacer(1, 2)] + _ar_paragraphs(text_ar, styles["notice_ar"], CONTENT_W - 24)
    t = Table([[body]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SAND),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("LINEBEFORE", (0, 0), (0, 0), 2.5, ZELLIGE),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    return t


def _build(output_path: Path, story: list, *, ref: str, host_name: str, title: str,
           headers: list[tuple[str, str]], total_pages: int) -> None:
    _register_fonts()
    counter = [0]

    def on_page(canvas, _doc):
        counter[0] += 1
        _draw_watermark(canvas)
        fr, ar_title = headers[min(counter[0] - 1, len(headers) - 1)]
        _draw_header(canvas, fr, ar_title)
        _draw_footer(canvas, counter[0], total_pages, ref, host_name)

    doc = BaseDocTemplate(str(output_path), pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
                          topMargin=HEADER_H, bottomMargin=FOOTER_H + 0.4 * cm, title=title, author=settings.app_name)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=on_page)])
    doc.build(story)


def _host_name(submission: Submission) -> str:
    section = getattr(submission, "section", None)
    return section.name if section else ""


def _submitted(submission: Submission) -> datetime:
    when = submission.submitted_at or datetime.utcnow()
    return when.replace(tzinfo=None) if when.tzinfo else when


# ---------------------------------------------------------------- fiche de police


def generate_fiche_pdf(submission: Submission, property_address: str, apartment_name: str,
                       signature_file: Path, output_path: Path) -> None:
    _register_fonts()
    styles = _styles()
    submitted = _submitted(submission)
    accepted = "Oui — lu et accepté"
    story = [
        _title_block("FICHE INDIVIDUELLE DE POLICE", "استمارة تسجيل النزيل",
                     "Déclaration d'arrivée d'un voyageur — hébergement de courte durée", styles),
        _meta_row(submission, submitted, styles),
        Spacer(1, 3.2 * mm),
        _section("I", "HÉBERGEMENT", "الإيواء", [
            ("Établissement", apartment_name, "المؤسسة"),
            ("Adresse complète", property_address, "العنوان الكامل"),
            ("Exploitant / hôte", _host_name(submission), "المستغل"),
        ], styles),
        Spacer(1, 2.6 * mm),
        _section("II", "IDENTITÉ DU VOYAGEUR", "هوية النزيل", [
            ("Nom de famille", submission.last_name, "الاسم العائلي"),
            ("Prénom(s)", submission.first_name, "الاسم الشخصي"),
            ("Nationalité", submission.nationality, "الجنسية"),
            ("Date de naissance", submission.date_of_birth, "تاريخ الازدياد"),
            ("Pays de résidence", submission.country_of_residence, "بلد الإقامة"),
        ], styles),
        Spacer(1, 2.6 * mm),
        _section("III", "SÉJOUR ET PIÈCE D'IDENTITÉ", "الإقامة ووثيقة الهوية", [
            ("Date d'arrivée", submission.arrival_date, "تاريخ الوصول"),
            ("Date de départ", submission.departure_date, "تاريخ المغادرة"),
            ("Nombre de voyageurs", str(submission.number_of_guests), "عدد النزلاء"),
            ("Dont enfants", str(submission.number_of_kids), "منهم أطفال"),
            ("Type de pièce", submission.id_document_type, "نوع الوثيقة"),
            ("Numéro de la pièce", submission.id_document_number, "رقم الوثيقة"),
        ], styles),
        Spacer(1, 2.6 * mm),
        _section("IV", "DÉCLARATIONS", "التصريحات", [
            ("Règlement intérieur", accepted if submission.accept_internal_rules else "—", "النظام الداخلي"),
            ("Conditions générales", accepted if submission.accept_terms else "—", "الشروط العامة"),
        ], styles),
        Spacer(1, 3.2 * mm),
        _signatures(signature_file, styles, "Signature du voyageur", "توقيع النزيل"),
        Spacer(1, 3 * mm),
        _notice(
            "Le/la soussigné(e) certifie l'exactitude des renseignements ci-dessus et accepte les obligations "
            "légales en vigueur au Royaume du Maroc relatives à l'hébergement des voyageurs.",
            "يشهد الموقع أدناه بصحة المعلومات المذكورة أعلاه ويقبل الالتزامات القانونية الجاري بها العمل في المملكة المغربية المتعلقة بإيواء المسافرين.",
            styles,
        ),
    ]
    _build(output_path, story, ref=submission.public_id[:8].upper(), host_name=_host_name(submission),
           title="Fiche individuelle de police", headers=[("FICHE DE POLICE", "")], total_pages=1)


# ---------------------------------------------------------------- règlement intérieur


def _split_rules(text: str) -> tuple[str | None, list[tuple[str, list[str]]]]:
    """(document title, [(article title, body lines)]) from the rules text files."""
    title, articles = None, []
    for raw in (text or "").strip().splitlines():
        line = raw.strip()
        if not line:
            continue
        if title is None and not line[0].isdigit():
            title = line
        elif re.match(r"^\d+[.)]", line):
            articles.append((line, []))
        elif articles:
            articles[-1][1].append(line)
    return title, articles


def _guest_block(submission: Submission, apartment_name: str, apartment_address: str, styles: dict,
                 lang: str = "fr") -> Table:
    place = apartment_name if not apartment_address or apartment_address == apartment_name else f"{apartment_name}, {apartment_address}"
    t = {"fr": ("VOYAGEUR ET SÉJOUR", "Voyageur", "Établissement", "Séjour"),
         "en": ("GUEST AND STAY", "Guest", "Property", "Stay")}[lang]
    return _section("", t[0], "النزيل والإقامة", [
        (t[1], f"{submission.first_name} {submission.last_name}", "النزيل"),
        (t[2], place, "المؤسسة"),
        (t[3], f"{submission.arrival_date} → {submission.departure_date}", "مدة الإقامة"),
    ], styles)


def _rules_page_latin(submission, apartment_name, apartment_address, rules_text, heading, attest_fr, sig_label,
                     signature_file, styles, lang="fr"):
    doc_title, articles = _split_rules(rules_text)
    story = [_title_block(heading[0], heading[1], doc_title or "", styles),
             _guest_block(submission, apartment_name, apartment_address, styles, lang), Spacer(1, 2 * mm)]
    for art_title, body in articles:
        story.append(Paragraph(
            f'<font name="Helvetica-Bold" color="#7A3319">{_escape(art_title)}</font>&nbsp; {_escape(" ".join(body))}',
            styles["article_inline"],
        ))
    story += [Spacer(1, 2.5 * mm), _attest(attest_fr, styles),
              Spacer(1, 2.5 * mm),
              _signatures(signature_file, styles, sig_label, "توقيع النزيل",
                          "Host stamp" if lang == "en" else "Cachet de l'établissement")]
    return story


def _attest(text: str, styles: dict) -> Table:
    t = Table([[Paragraph(text, styles["notice"])]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SAND), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("LINEBEFORE", (0, 0), (0, 0), 2.5, ZELLIGE),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    return t


def _rules_page_arabic(submission, apartment_name, apartment_address, rules_text, signature_file, styles):
    doc_title, articles = _split_rules(rules_text)
    story = [_title_block("RÈGLEMENT INTÉRIEUR — VERSION ARABE", "النظام الداخلي", "", styles),
             _guest_block(submission, apartment_name, apartment_address, styles), Spacer(1, 2 * mm)]
    if doc_title:
        story += _ar_paragraphs(doc_title, styles["article_title_ar"], CONTENT_W)
    for art_title, body in articles:
        story += _ar_paragraphs(art_title, styles["article_title_ar"], CONTENT_W)
        if body:
            story += _ar_paragraphs(" ".join(body), styles["article_body_ar"], CONTENT_W)
    name = f"{submission.first_name} {submission.last_name}"
    attest = (f"أنا الموقع(ة) أدناه {name}، أصرح بأنني اطلعت على هذا النظام الداخلي بالكامل وألتزم باحترامه "
              "طوال مدة الإقامة، تحت طائلة فسخ العقد واتخاذ الإجراءات القانونية وفق القانون المغربي الجاري به العمل.")
    box = Table([[_ar_paragraphs(attest, styles["notice_ar"], CONTENT_W - 24)]], colWidths=[CONTENT_W])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SAND), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("LINEAFTER", (0, 0), (0, 0), 2.5, ZELLIGE),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story += [Spacer(1, 3 * mm), box, Spacer(1, 3 * mm),
              _signatures(signature_file, styles, "Signature du voyageur", "توقيع النزيل")]
    return story


PAGE_CONTENT_MAX_H = 23.7 * cm  # frame height is 24.05 cm


def _one_page(story: list) -> KeepInFrame:
    """Keep rules + declaration + signature on a single page (scaled down only if the text is long)."""
    return KeepInFrame(CONTENT_W, PAGE_CONTENT_MAX_H, story, mode="shrink", hAlign="LEFT", vAlign="TOP")


def generate_rules_pdf(submission: Submission, apartment_name: str, apartment_address: str,
                       signature_file: Path, output_path: Path) -> None:
    _register_fonts()
    styles = _styles()
    name = f"<b>{_escape(submission.first_name)} {_escape(submission.last_name)}</b>"
    story = [_one_page(_rules_page_latin(
        submission, apartment_name, apartment_address, settings.load_rules_fr(),
        ("RÈGLEMENT INTÉRIEUR", "النظام الداخلي"),
        f"Je soussigné(e), {name}, déclare avoir pris connaissance de l'intégralité du présent règlement et "
        "m'engage à le respecter pendant toute la durée du séjour, sous peine de résiliation du contrat et de "
        "poursuites conformément à la loi marocaine en vigueur.",
        "Signature du voyageur", signature_file, styles))]
    story.append(PageBreak())
    story += [_one_page(_rules_page_latin(
        submission, apartment_name, apartment_address, settings.load_rules_en(),
        ("HOUSE RULES — ENGLISH VERSION", "النظام الداخلي"),
        f"I, the undersigned, {name}, declare that I have read these rules in full and agree to comply with them "
        "throughout my stay, failing which the rental agreement may be terminated and legal action taken under "
        "applicable Moroccan law.",
        "Guest signature", signature_file, styles, lang="en"))]
    pages = 2
    rules_ar = settings.load_rules_ar()
    if rules_ar.strip():
        story.append(PageBreak())
        story += [_one_page(_rules_page_arabic(submission, apartment_name, apartment_address, rules_ar, signature_file, styles))]
        pages = 3
    _build(output_path, story, ref=submission.public_id[:8].upper(), host_name=_host_name(submission),
           title="Règlement intérieur signé", headers=[("RÈGLEMENT", "")], total_pages=pages)
