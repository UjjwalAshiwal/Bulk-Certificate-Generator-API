"""ReportLab certificate PDF generation (the predefined template, in code)."""

import io

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

WIDTH, HEIGHT = landscape(A4)


def render_certificate_pdf(
    *,
    recipient_name: str,
    event_name: str,
    event_date: str,
    issuer_name: str,
    certificate_id: str,
) -> bytes:
    """Render a single certificate PDF. Raises on empty required content."""
    if not recipient_name or not recipient_name.strip():
        raise ValueError("recipient_name must not be empty")
    if not certificate_id or not certificate_id.strip():
        raise ValueError("certificate_id must not be empty")
    # The built-in Helvetica font only covers Latin-1. Failing loudly here
    # routes the recipient to FAILED with a clear reason instead of silently
    # issuing a certificate with a blank/garbled name.
    for label, value in (
        ("recipient_name", recipient_name),
        ("event_name", event_name),
        ("issuer_name", issuer_name),
        ("certificate_id", certificate_id),
    ):
        try:
            value.encode("latin-1")
        except UnicodeEncodeError as exc:
            raise ValueError(
                f"{label} contains characters the certificate font cannot render"
            ) from exc

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))

    # Border
    c.setLineWidth(3)
    c.rect(12 * mm, 12 * mm, WIDTH - 24 * mm, HEIGHT - 24 * mm)
    c.setLineWidth(0.75)
    c.rect(15 * mm, 15 * mm, WIDTH - 30 * mm, HEIGHT - 30 * mm)

    cx = WIDTH / 2
    y = HEIGHT - 45 * mm
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(cx, y, "CERTIFICATE OF COMPLETION")

    y -= 16 * mm
    c.setFont("Helvetica", 13)
    c.drawCentredString(cx, y, "This certificate is proudly presented to")

    y -= 16 * mm
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(cx, y, recipient_name.strip())

    y -= 12 * mm
    c.setFont("Helvetica", 13)
    c.drawCentredString(cx, y, "for successfully participating in")

    y -= 12 * mm
    c.setFont("Helvetica-Bold", 17)
    c.drawCentredString(cx, y, event_name)

    y -= 10 * mm
    c.setFont("Helvetica", 13)
    c.drawCentredString(cx, y, f"on {event_date}")

    y -= 14 * mm
    c.setFont("Helvetica", 12)
    c.drawCentredString(cx, y, f"Issued by {issuer_name}")

    c.setFont("Helvetica", 11)
    c.drawCentredString(cx, 30 * mm, f"Certificate ID: {certificate_id}")

    c.showPage()
    c.save()
    return buf.getvalue()
