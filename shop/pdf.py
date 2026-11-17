import io
import os
from xml.sax.saxutils import escape

import qrcode
from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INK = colors.HexColor("#2a1a12")
MUTED = colors.HexColor("#7a6a5f")
LINE = colors.HexColor("#e6ded6")
CREAM = colors.HexColor("#f8f4ee")
CARAMEL = colors.HexColor("#b08968")

FONT_CANDIDATES = {
    "regular": ["DejaVuSans.ttf", "arial.ttf"],
    "bold": ["DejaVuSans-Bold.ttf", "arialbd.ttf"],
}
FONT_DIRS = [
    os.path.join(settings.BASE_DIR, "shop", "static", "fonts"),
    "/usr/share/fonts/truetype/dejavu",
    r"C:\Windows\Fonts",
]


def _find_font(kind):
    for directory in FONT_DIRS:
        for filename in FONT_CANDIDATES[kind]:
            path = os.path.join(directory, filename)
            if os.path.exists(path):
                return path
    return None


def _register_fonts():
    regular = _find_font("regular")
    bold = _find_font("bold") or regular
    if not regular:
        return "Helvetica", "Helvetica-Bold"
    if "CafeFont" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("CafeFont", regular))
        pdfmetrics.registerFont(TTFont("CafeFont-Bold", bold))
    return "CafeFont", "CafeFont-Bold"


def build_receipt_pdf(order):
    """Чек заказа кофейни с QR-кодом на публичную страницу статуса."""
    regular, bold = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A5,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Чек {order.number}",
    )
    base = getSampleStyleSheet()
    title = ParagraphStyle("CafeTitle", parent=base["Title"], fontName=bold, fontSize=17, leading=20, textColor=INK)
    subtitle = ParagraphStyle("CafeSub", parent=base["Normal"], fontName=regular, fontSize=8.5, leading=12, alignment=TA_CENTER, textColor=MUTED)
    normal = ParagraphStyle("CafeNormal", parent=base["Normal"], fontName=regular, fontSize=9.5, leading=13, textColor=INK, alignment=TA_LEFT)
    small = ParagraphStyle("CafeSmall", parent=base["Normal"], fontName=regular, fontSize=7.5, leading=10, textColor=MUTED)
    right = ParagraphStyle("CafeRight", parent=normal, alignment=TA_RIGHT)

    def money(value):
        return f"{value:,.2f} ₽".replace(",", " ")

    story = [
        Paragraph("☕ ЗЕРНО", title),
        Paragraph(
            "кофейня и обжарка · Москва, ул. Кофейная, 7<br/>"
            "+7 (495) 000-00-07 · зерно@cafe.local<br/>"
            "Ежедневно 08:00–22:00",
            subtitle,
        ),
        Spacer(1, 5 * mm),
        Paragraph(f"<b>Чек {order.number}</b>", normal),
        Paragraph(
            f"{timezone.localtime(order.created_at):%d.%m.%Y %H:%M} · "
            f"статус: {escape(order.get_status_display())}",
            small,
        ),
        Spacer(1, 3 * mm),
    ]

    rows = [[
        Paragraph("<b>Наименование</b>", normal),
        Paragraph("<b>Кол-во</b>", normal),
        Paragraph("<b>Цена</b>", normal),
        Paragraph("<b>Сумма</b>", normal),
    ]]
    for item in order.items.all():
        rows.append([
            Paragraph(escape(item.name), normal),
            Paragraph(str(item.quantity), normal),
            Paragraph(money(item.price), normal),
            Paragraph(money(item.total), normal),
        ])
    rows.append([Paragraph("<b>Итого</b>", normal), "", "", Paragraph(f"<b>{money(order.total)}</b>", normal)])
    table = Table(rows, colWidths=[58 * mm, 15 * mm, 27 * mm, 27 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), regular),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("BACKGROUND", (0, 0), (-1, 0), CREAM),
                ("SPAN", (0, -1), (2, -1)),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 3 * mm))

    details = []
    if order.pickup_time:
        details.append(
            f"Самовывоз: {timezone.localtime(order.pickup_time):%d.%m.%Y %H:%M}"
        )
    if order.comment:
        details.append(f"Комментарий: {escape(order.comment)}")
    if order.stickers.exists():
        details.append("Дизайн стакана: " + ", ".join(s.sticker.symbol for s in order.stickers.all()))
    if details:
        story.append(Paragraph("<br/>".join(details), small))
        story.append(Spacer(1, 2 * mm))

    qr_value = f"{settings.SITE_URL}/order/{order.public_token}/"
    qr_image = qrcode.make(qr_value)
    qr_buffer = io.BytesIO()
    qr_image.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    qr = Image(qr_buffer, width=26 * mm, height=26 * mm)
    qr_block = Table(
        [[qr, Paragraph(
            "Покажите QR-код на кассе или откройте страницу заказа — там актуальный статус "
            "изготовления и состав заказа.",
            small,
        )]],
        colWidths=[30 * mm, 97 * mm],
    )
    qr_block.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)])
    )
    story.append(qr_block)
    story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(
            "Спасибо, что выбрали «Зерно»! Чек сформирован автоматически и не требует подписи. "
            "Горячие напитки рекомендуем забрать в течение 15 минут после статуса «Готов к выдаче».",
            small,
        )
    )
    doc.build(story)
    return buffer.getvalue()
