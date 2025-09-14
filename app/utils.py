# app/utils.py

import qrcode
import io
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

# ---------------- QR Code Generator ----------------
def generate_qr_code(data: str):
    """
    Generate a QR code image (PNG) in memory.
    Returns a BytesIO object.
    """
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
    buf.seek(0)
    return buf


# ---------------- ID Card PDF Generator ----------------
def generate_idcard_pdf(name: str, ieee_id: str, qr_data: str, output_path: str = None):
    """
    Generate a simple ID card PDF with name, ieee_id, and QR code.
    """
    # Default path
    if output_path is None:
        output_path = f"idcard_{ieee_id}.pdf"

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
    qr_buf = generate_qr_code(qr_data)
    qr_path = f"qr_{ieee_id}.png"
    with open(qr_path, "wb") as f:
        f.write(qr_buf.read())
    c.drawImage(qr_path, 100, height - 300, width=100, height=100)

    # Save PDF
    c.save()

    # Cleanup QR image
    if os.path.exists(qr_path):
        os.remove(qr_path)

    return output_path
