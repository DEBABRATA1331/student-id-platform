import os
import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor

# ---------------- QR Code Generation ----------------
def generate_qr_code(name, ieee_id):
    qr_data = f"{name} | IEEE ID: {ieee_id}"
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(qr_data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    qr_filename = f"{name.replace(' ', '_')}_qr.png"
    qr_path = os.path.join("app/static/qrcodes", qr_filename)
    img.save(qr_path)

    return qr_filename


# ---------------- PDF Generation (Stylish ID Card) ----------------
def generate_idcard_pdf(student):
    pdf_filename = f"{student['name'].replace(' ', '_')}_ID_Card.pdf"
    pdf_path = os.path.join("app/static/qrcodes", pdf_filename)

    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    # ----------- Card Dimensions -----------
    card_x = 100
    card_y = height - 420
    card_width = 380
    card_height = 260

    # ----------- Shadow -----------
    c.setFillColor(HexColor("#d9d9d9"))
    c.roundRect(card_x + 5, card_y - 5, card_width, card_height, 15, fill=True, stroke=0)

    # ----------- Card Background -----------
    c.setFillColor(HexColor("#ffffff"))
    c.roundRect(card_x, card_y, card_width, card_height, 15, fill=True, stroke=0)

    # ----------- Border -----------
    c.setStrokeColor(HexColor("#185a9d"))
    c.setLineWidth(2)
    c.roundRect(card_x, card_y, card_width, card_height, 15, fill=0, stroke=1)

    # ----------- Header -----------
    header_height = 45
    c.setFillColor(HexColor("#5b86e5"))
    c.roundRect(card_x, card_y + card_height - header_height, card_width, header_height, 15, fill=True, stroke=0)
    c.setFillColor(HexColor("#ffffff"))
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(card_x + card_width / 2, card_y + card_height - 28, "STUDENT ID CARD")

    # ----------- Organization Logo -----------
    logo_path = os.path.join("app/static/images", "logo.png")
    if os.path.exists(logo_path):
        logo = ImageReader(logo_path)
        c.drawImage(logo, card_x + 15, card_y + card_height - 80, width=50, height=50, mask='auto')

    # ----------- Organization Name -----------
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(HexColor("#185a9d"))
    c.drawString(card_x + 75, card_y + card_height - 60, "YOUR ORGANIZATION NAME")

    # ----------- Student Details -----------
    c.setFillColor(HexColor("#000000"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(card_x + 20, card_y + card_height - 100, f"Name: {student['name']}")
    c.setFont("Helvetica", 11)
    c.drawString(card_x + 20, card_y + card_height - 120, f"Domain: {student['domain']}")
    c.drawString(card_x + 20, card_y + card_height - 140, f"Joining Date: {student['joining_date']}")
    c.drawString(card_x + 20, card_y + card_height - 160, f"Category: {student['category']}")
    c.drawString(card_x + 20, card_y + card_height - 180, f"IEEE ID: {student['ieee_id']}")

    # ----------- QR Code -----------
    qr_path = os.path.join("app/static/qrcodes", student["qr_code"])
    if os.path.exists(qr_path):
        qr = ImageReader(qr_path)
        c.drawImage(qr, card_x + card_width - 120, card_y + 40, width=90, height=90)

    c.showPage()
    c.save()
    return pdf_filename
