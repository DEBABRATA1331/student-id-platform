# app/utils.py

import qrcode
import io
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

# ---------------- QR Code Generator ----------------
def generate_qr_code(name: str, ieee_id: str) -> bytes:
    """
    Generate a QR code as bytes using name and IEEE ID.
    Returns PNG bytes suitable for storing in SQLite BLOB.
    """
    data = f"Name: {name}, IEEE ID: {ieee_id}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()  # Return raw bytes for database storage


# ---------------- ID Card PDF Generator ----------------
def generate_idcard_pdf(name: str, ieee_id: str, qr_bytes: bytes = None, output_path: str = None):
    """
    Generate a simple ID card PDF with name, ieee_id, and QR code.
    If qr_bytes is not provided, it will generate a new QR code.
    """
    # Default path
    if output_path is None:
        output_path = f"idcard_{ieee_id}.pdf"

    if qr_bytes is None:
        qr_bytes = generate_qr_code(name, ieee_id)

    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4

    # Title
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 80, "IEEE Student ID Card")

    # Student info
    c.setFont("Helvetica", 12)
    c.drawString(100, height - 150, f"Name: {name}")
    c.drawString(100, height - 170, f"IEEE ID: {ieee_id}")

    # QR Code
    qr_image = ImageReader(io.BytesIO(qr_bytes))
    c.drawImage(qr_image, 100, height - 300, width=100, height=100)

    # Save PDF
    c.save()

    return output_path
