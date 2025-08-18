from flask import render_template, request, redirect, url_for, session, flash, send_from_directory
from app import app
import os
import pandas as pd
import random
import sqlite3
from app.models import clear_and_insert_students
from app.utils import generate_qr_code, generate_idcard_pdf
import threading
import io
import csv

# ---------------- CONFIG ----------------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("static/attendance_reports", exist_ok=True)

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

# ---------------- ATTENDANCE ----------------
# In-memory storage for active attendance sessions
# Format: {event_date: {student_id: status}}
active_attendance = {}

def end_attendance(event_date):
    """Automatically save attendance CSV after session ends."""
    if event_date in active_attendance:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Student ID", "Status"])
        for sid, status in active_attendance[event_date].items():
            writer.writerow([sid, status])
        report_file = f"attendance_{event_date}.csv"
        with open(os.path.join("static/attendance_reports", report_file), "w", newline="") as f:
            f.write(output.getvalue())
        print(f"Attendance session for {event_date} ended. Report saved!")
        del active_attendance[event_date]  # Remove session after saving

# ---------------- HOME ----------------
@app.route('/')
def home():
    admin_manual = os.path.exists(os.path.join(app.static_folder, "admin_manual.pdf"))
    student_manual = os.path.exists(os.path.join(app.static_folder, "student_manual.pdf"))

    societies = [
        {"name": "IEEE CASS", "logo": "cass.png"},
        {"name": "IEEE COMSOC", "logo": "comsoc.png"},
        {"name": "IEEE WIE", "logo": "wie.png"},
        {"name": "IEEE Sensor Council", "logo": "sensor.png"},
        {"name": "IEEE Computer Society", "logo": "computer.png"}
    ]

    announcements = [
        {"title": "Workshop on Robotics", "date": "2025-08-15", "description": "Join us for a hands-on robotics workshop."},
        {"title": "IEEE Day Celebration", "date": "2025-10-02", "description": "Mark your calendars for IEEE Day 2025 events."}
    ]

    return render_template("home.html", admin_manual=admin_manual,
                           student_manual=student_manual,
                           societies=societies,
                           announcements=announcements)

# ---------------- ADMIN ROUTES ----------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin"] = True
            flash("Login successful!", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid credentials!", "danger")
    return render_template("login.html")

@app.route("/admin/dashboard", methods=["GET", "POST"])
def admin_dashboard():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    # Handle CSV upload
    if request.method == "POST":
        file = request.files.get("csv_file")
        if file and file.filename.endswith(".csv"):
            filepath = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(filepath)

            df = pd.read_csv(filepath)
            students = []
            for _, row in df.iterrows():
                qr_file = generate_qr_code(row["Name"], row["IEEE ID"])
                students.append({
                    "Name": row["Name"],
                    "Domain": row["Domain"],
                    "Joining Date": row["Joining Date"],
                    "Category": row["Category"],
                    "IEEE ID": row["IEEE ID"],
                    "QR": qr_file
                })
            clear_and_insert_students(students)
            flash("CSV uploaded and QR codes generated successfully!", "success")
        else:
            flash("Please upload a valid CSV file.", "danger")

    # Attendance report files
    attendance_files = os.listdir('static/attendance_reports') if os.path.exists('static/attendance_reports') else []

    return render_template("dashboard.html", attendance_files=attendance_files)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    flash("Logged out successfully!", "info")
    return redirect(url_for("admin_login"))

# ---------------- ATTENDANCE ROUTES ----------------
@app.route("/admin/start_attendance")
def admin_start_attendance():
    """Admin starts attendance for a given date from dashboard."""
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    event_date = request.args.get("event_date")
    if not event_date:
        flash("Please select a date to start attendance.", "warning")
        return redirect(url_for("admin_dashboard"))

    if event_date in active_attendance:
        flash("Attendance session already active!", "warning")
    else:
        active_attendance[event_date] = {}
        threading.Timer(180, end_attendance, args=[event_date]).start()
        flash(f"Attendance session for {event_date} started! Students have 3 minutes.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/attendance/<event_date>")
def attendance_page(event_date):
    """Student-facing attendance page to mark themselves present/absent."""
    conn = sqlite3.connect(os.path.join("instance", "students.db"))
    c = conn.cursor()
    c.execute("SELECT id, name FROM students")
    students = c.fetchall()
    conn.close()

    return render_template("attendance.html", event_date=event_date, students=students)

@app.route("/attendance/mark/<event_date>/<int:student_id>")
def mark_attendance(event_date, student_id):
    """Student marks themselves present."""
    if event_date in active_attendance:
        active_attendance[event_date][student_id] = "Present"
        return f"{student_id} marked as Present for {event_date}"
    return "Attendance session not active!"

# ---------------- USER ROUTES ----------------
@app.route("/user/search", methods=["GET", "POST"])
def user_search():
    if request.method == "POST":
        user_answer = request.form.get("captcha_answer")
        correct_answer = session.get("captcha_result")

        if str(user_answer) != str(correct_answer):
            flash("❌ Incorrect CAPTCHA! Please try again.", "danger")
            return redirect(url_for("user_search"))

        name = request.form.get("name").strip()
        conn = sqlite3.connect(os.path.join("instance", "students.db"))
        c = conn.cursor()
        c.execute("SELECT * FROM students WHERE name LIKE ?", (f"%{name}%",))
        student = c.fetchone()
        conn.close()

        if student:
            return redirect(url_for("user_idcard", student_id=student[0]))
        else:
            flash("⚠ No student found with that name!", "warning")
            return redirect(url_for("user_search"))

    num1 = random.randint(1, 9)
    num2 = random.randint(1, 9)
    session["captcha_result"] = num1 + num2

    return render_template("search.html", num1=num1, num2=num2)

@app.route("/user/idcard/<int:student_id>")
def user_idcard(student_id):
    conn = sqlite3.connect(os.path.join("instance", "students.db"))
    c = conn.cursor()
    c.execute("SELECT * FROM students WHERE id = ?", (student_id,))
    student = c.fetchone()
    conn.close()

    if student:
        student_data = {
            "id": student[0],
            "name": student[1],
            "domain": student[2],
            "joining_date": student[3],
            "category": student[4],
            "ieee_id": student[5],
            "qr_code": student[6]
        }
        return render_template("idcard.html", student=student_data)
    else:
        flash("⚠ Student not found!", "warning")
        return redirect(url_for("user_search"))

@app.route("/user/download/<int:student_id>")
def user_download(student_id):
    conn = sqlite3.connect(os.path.join("instance", "students.db"))
    c = conn.cursor()
    c.execute("SELECT * FROM students WHERE id = ?", (student_id,))
    student = c.fetchone()
    conn.close()

    if student:
        student_data = {
            "id": student[0],
            "name": student[1],
            "domain": student[2],
            "joining_date": student[3],
            "category": student[4],
            "ieee_id": student[5],
            "qr_code": student[6]
        }

        pdf_file = generate_idcard_pdf(student_data)
        pdf_path = os.path.join(app.root_path, "static", "qrcodes", pdf_file)

        if not os.path.exists(pdf_path):
            flash("⚠ PDF not generated! Try again.", "warning")
            return redirect(url_for("user_idcard", student_id=student_id))

        return send_from_directory(
            directory=os.path.join(app.root_path, "static", "qrcodes"),
            path=pdf_file,
            as_attachment=True
        )
    else:
        flash("⚠ Student not found!", "warning")
        return redirect(url_for("user_search"))
