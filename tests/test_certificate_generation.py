"""Certificate generation: real PDFs with recipient-specific content."""

import base64
import re
import zlib

from app.services.certificate_service import render_certificate_pdf


def _decode_stream(raw: bytes) -> bytes:
    """ReportLab emits ASCII85 + Flate streams ending in '~>'; stdlib-decodable."""
    raw = raw.strip()
    if raw.endswith(b"~>"):
        raw = raw[:-2]
    return zlib.decompress(base64.a85decode(raw, adobe=False))
    """Decompress page streams (stdlib only) so assertions check real content."""


def _pdf_text(pdf: bytes) -> bytes:
    out = b""
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.DOTALL):
        raw = m.group(1).strip()
        for attempt in (
            lambda: _decode_stream(raw),
            lambda: zlib.decompress(raw),
            lambda: raw,
        ):
            try:
                out += attempt()
                break
            except Exception:
                continue
    return out


def test_pdf_is_generated_nonempty_and_valid():
    pdf = render_certificate_pdf(
        recipient_name="Ujjwal Ashiwal",
        event_name="Python Bootcamp 2026",
        event_date="2026-10-07",
        issuer_name="Example Organization",
        certificate_id="CERT-001",
    )
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


def test_pdf_contains_recipient_specific_data():
    pdf = render_certificate_pdf(
        recipient_name="Ujjwal Ashiwal",
        event_name="Python Bootcamp 2026",
        event_date="2026-10-07",
        issuer_name="Example Organization",
        certificate_id="CERT-001",
    )
    text = _pdf_text(pdf)
    assert b"Ujjwal Ashiwal" in text
    assert b"Python Bootcamp 2026" in text
    assert b"CERT-001" in text


def test_different_recipients_yield_different_pdfs():
    kwargs = dict(
        event_name="Python Bootcamp 2026",
        event_date="2026-10-07",
        issuer_name="Example Organization",
    )
    a = render_certificate_pdf(recipient_name="Alice", certificate_id="CERT-A", **kwargs)
    b = render_certificate_pdf(recipient_name="Bob", certificate_id="CERT-B", **kwargs)
    assert a != b
    assert b"Bob" in _pdf_text(b)
    assert b"Alice" not in _pdf_text(b)
