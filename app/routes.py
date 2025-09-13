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
active_attendance = {}

def end_attendance(event_date):
    if event_date in active_attendance:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Student ID", "Status"])
        for sid, status in active_attendance[event_date].items():
            writer.writerow([sid, status])
        report_file = f"attendance_{event_date}.csv"
        with open(os.path.join("static/attendance_reports", report_file), "w", newline="") as f:
            f.write(output.getvalue())
        del active_attendance[event_date]

# ---------------- HOME ----------------
@app.route('/')
def home():
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

    # Check for active attendance session
    active_event_date = None
    if active_attendance:
        # pick the latest active event
        active_event_date = sorted(active_attendance.keys())[-1]

    return render_template(
        "home.html",
        societies=societies,
        announcements=announcements,
        active_event_date=active_event_date
    )

# ---------------- ADMIN ----------------
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

    # ---------------- Handle CSV Upload ----------------
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

    # ---------------- Attendance Files ----------------
    attendance_files = os.listdir('static/attendance_reports') if os.path.exists('static/attendance_reports') else []

    # ---------------- Recent CSV Uploads ----------------
    recent_uploads = []
    if os.path.exists(UPLOAD_FOLDER):
        for f in sorted(os.listdir(UPLOAD_FOLDER), reverse=True)[:5]:
            recent_uploads.append({
                "filename": f,
                "uploaded_on": pd.to_datetime(os.path.getmtime(os.path.join(UPLOAD_FOLDER, f)), unit='s').strftime("%Y-%m-%d %H:%M:%S"),
                "uploaded_by": "Admin"
            })

    # ---------------- Statistics ----------------
    conn = sqlite3.connect(os.path.join("instance", "students.db"))
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM students")
    total_students = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM students WHERE Category='Tech'")
    tech = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM students WHERE Category='Non-Tech'")
    non_tech = c.fetchone()[0]

    societies_list = ["CASS", "COMSOC", "WIE", "Sensor", "CS"]
    society_counts = {}
    for soc in societies_list:
        c.execute("SELECT COUNT(*) FROM students WHERE Domain LIKE ?", (f"%{soc}%",))
        society_counts[soc.lower()] = c.fetchone()[0]

    # ---------------- Search Functionality ----------------
    query = request.args.get("query")
    search_results = []
    if query:
        c.execute(
            "SELECT id, name, Domain, [IEEE ID] FROM students WHERE name LIKE ? OR [IEEE ID] LIKE ?", 
            (f"%{query}%", f"%{query}%")
        )
        rows = c.fetchall()
        for row in rows:
            search_results.append({
                "id": row[0],
                "name": row[1],
                "domain": row[2],
                "ieee_id": row[3]
            })

    conn.close()

    stats = {
        "total_students": total_students,
        "total_id_cards": total_students,
        "tech": tech,
        "non_tech": non_tech,
        **society_counts
    }

    return render_template(
        "dashboard.html",
        attendance_files=attendance_files,
        stats=stats,
        recent_uploads=recent_uploads,
        search_results=search_results
    )

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    flash("Logged out successfully!", "info")
    return redirect(url_for("admin_login"))

# ---------------- ATTENDANCE ----------------
@app.route("/admin/start_attendance")
def admin_start_attendance():
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

# ---------------- ATTENDANCE ----------------
@app.route("/attendance/<event_date>", methods=["GET", "POST"])
def attendance(event_date):
    conn = sqlite3.connect(os.path.join("instance", "students.db"))
    c = conn.cursor()

    if request.method == "POST":
        student_id = request.form.get("student_id")
        status = request.form.get("status")  # "Present" or "Absent"

        if not student_id:
            flash("⚠ Invalid student ID!", "danger")
            return redirect(url_for("attendance", event_date=event_date))

        # Store in active_attendance (temporary session)
        if event_date in active_attendance:
            active_attendance[event_date][student_id] = status

        # Store in DB
        c.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                event_date TEXT,
                status TEXT
            )
        """)
        c.execute(
            "INSERT INTO attendance (student_id, event_date, status) VALUES (?, ?, ?)",
            (student_id, event_date, status)
        )
        conn.commit()
        flash(f"✅ Attendance marked as {status} for Student {student_id}", "success")
        return redirect(url_for("attendance", event_date=event_date))

    # GET request → show all students
    c.execute("SELECT id, name FROM students")
    students = c.fetchall()

    # Fetch attendance records for this event_date
    c.execute("SELECT student_id, status FROM attendance WHERE event_date = ?", (event_date,))
    attendance_records_db = c.fetchall()

    # Merge with student names and calculate counts
    attendance_records = []
    present_count = 0
    absent_count = 0
    for rec in attendance_records_db:
        student_id, status = rec
        name = next((s[1] for s in students if s[0] == student_id), "Unknown")
        attendance_records.append({"student_id": student_id, "name": name, "status": status})
        if status == "Present":
            present_count += 1
        elif status == "Absent":
            absent_count += 1

    attendance_summary = {
        "total": len(attendance_records),
        "present": present_count,
        "absent": absent_count
    }

    conn.close()

    return render_template(
        "attendance.html",
        event_date=event_date,
        students=students,
        attendance_records=attendance_records,
        attendance_summary=attendance_summary
    )




@app.route("/attendance/mark/<event_date>/<int:student_id>")
def mark_attendance(event_date, student_id):
    if event_date in active_attendance:
        active_attendance[event_date][student_id] = "Present"
        return f"{student_id} marked as Present for {event_date}"
    return "Attendance session not active!"

# ---------------- USER ----------------
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
