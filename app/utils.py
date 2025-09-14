from flask import render_template, request, redirect, url_for, flash, session, send_file
from app import app
import sqlite3, os, datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

DB = "app/database.db"

# ---------------- Admin: Start Attendance Session ----------------
@app.route("/admin/start_attendance", methods=["POST"])
def start_attendance():
    start_time = datetime.datetime.now()
    end_time = start_time + datetime.timedelta(minutes=3)

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DELETE FROM attendance_session")  # allow only 1 active
    c.execute("INSERT INTO attendance_session (start_time, end_time, active) VALUES (?, ?, ?)",
              (start_time, end_time, 1))
    conn.commit()
    conn.close()

    flash("Attendance session started for 3 minutes!")
    return redirect(url_for("admin_dashboard"))


@app.route("/mark_attendance", methods=["POST"])
def mark_attendance():
    ieee_id = request.form.get("ieee_id")

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # Check active session
    c.execute("SELECT start_time, end_time FROM attendance_session WHERE active=1")
    session_data = c.fetchone()
    if not session_data:
        flash("No active attendance session.")
        return redirect(url_for("student_portal"))

    start_time_str, end_time_str = session_data
    start_time = datetime.datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S.%f")
    end_time = datetime.datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S.%f")

    now = datetime.datetime.now()
    if not (start_time <= now <= end_time):
        flash("Attendance window closed.")
        return redirect(url_for("student_portal"))

    # Mark present
    c.execute("INSERT OR IGNORE INTO attendance (ieee_id, timestamp) VALUES (?, ?)",
              (ieee_id, now))
    conn.commit()
    conn.close()

    flash("Attendance marked successfully!")
    return redirect(url_for("student_portal"))



# ---------------- Admin: Manual Attendance ----------------
@app.route("/admin/manual_attendance", methods=["POST"])
def manual_attendance():
    ieee_id = request.form.get("ieee_id")

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO attendance (ieee_id, timestamp) VALUES (?, ?)",
              (ieee_id, datetime.datetime.now()))
    conn.commit()
    conn.close()

    flash(f"Manual attendance marked for {ieee_id}")
    return redirect(url_for("admin_dashboard"))


# ---------------- Generate Attendance Report PDF ----------------
@app.route("/admin/attendance_report")
def attendance_report():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT name, ieee_id FROM students")
    students = c.fetchall()

    c.execute("SELECT ieee_id FROM attendance")
    present_ids = {row[0] for row in c.fetchall()}
    conn.close()

    pdf_filename = "attendance_report.pdf"
    pdf_path = os.path.join("app/static/reports", pdf_filename)

    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4
    y = height - 50

    c.setFont("Helvetica-Bold", 16)
    c.drawString(200, y, "Attendance Report")
    y -= 40

    for name, ieee_id in students:
        status = "Present" if ieee_id in present_ids else "Absent"
        c.setFont("Helvetica", 12)
        c.drawString(50, y, f"{name} ({ieee_id}) - {status}")
        y -= 20
        if y < 50:
            c.showPage()
            y = height - 50

    c.save()
    return send_file(pdf_path, as_attachment=True)
