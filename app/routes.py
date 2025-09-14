from flask import render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify
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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "../instance/students.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "../uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("static/attendance_reports", exist_ok=True)

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

# ---------------- ATTENDANCE ----------------
active_attendance = {}

def end_attendance(event_date):
    """Save attendance report and close session after timeout"""
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
        {"title": "Workshop on Robotics", "date": "2025-10-11", "description": "Join us for a hands-on robotics workshop."},
        {"title": "IEEE Day Celebration", "date": "2025-10-17", "description": "Mark your calendars for IEEE Day 2025 events."}
    ]

    active_event_date = None
    if active_attendance:
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

            # Clean headers
            df.columns = df.columns.str.strip().str.lower()

            students = []
            for _, row in df.iterrows():
                qr_file = generate_qr_code(row["name"], row["ieee_id"])
                students.append({
                    "Name": row["name"],
                    "Domain": row.get("domain", ""),
                    "Joining Date": row.get("joining_date", ""),
                    "Category": row.get("category", ""),
                    "IEEE ID": row["ieee_id"],
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

    # ---------------- Statistics + Search ----------------
    conn = sqlite3.connect(DATABASE)
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

    # -------- AJAX live refresh support --------
    if request.args.get("ajax") == "1":
        uploads_html = render_template("_uploads.html", recent_uploads=recent_uploads)
        attendance_html = render_template("_attendance_files.html", attendance_files=attendance_files)
        return jsonify({
            "uploads_html": uploads_html,
            "attendance_html": attendance_html
        })

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

# ---------------- ATTENDANCE ROUTES ----------------
@app.route("/attendance/<event_date>", methods=["GET", "POST"])
def attendance(event_date):
    if request.method == "POST":
        student_id = request.form["student_id"]
        status = request.form["status"]

        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO attendance (event_date, student_id, status) VALUES (?, ?, ?)",
            (event_date, student_id, status)
        )
        conn.commit()

        # Get updated attendance
        c.execute("SELECT a.student_id, s.name, a.status FROM attendance a JOIN students s ON a.student_id = s.id WHERE event_date = ?", (event_date,))
        records = c.fetchall()

        c.execute("SELECT COUNT(*), SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END), SUM(CASE WHEN status='Absent' THEN 1 ELSE 0 END) FROM attendance WHERE event_date = ?", (event_date,))
        total, present, absent = c.fetchone()
        conn.close()

        table_html = render_template("attendance_table.html", attendance_records=records)

        return jsonify({
            "summary": {"total": total or 0, "present": present or 0, "absent": absent or 0},
            "table_html": table_html
        })

    # GET → Render full page
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT id, name FROM students")
    students = c.fetchall()

    c.execute("SELECT a.student_id, s.name, a.status FROM attendance a JOIN students s ON a.student_id = s.id WHERE event_date = ?", (event_date,))
    attendance_records = c.fetchall()

    c.execute("SELECT COUNT(*), SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END), SUM(CASE WHEN status='Absent' THEN 1 ELSE 0 END) FROM attendance WHERE event_date = ?", (event_date,))
    total, present, absent = c.fetchone()
    conn.close()

    summary = {"total": total or 0, "present": present or 0, "absent": absent or 0}
    return render_template("attendance.html", event_date=event_date, students=students, attendance_records=attendance_records, attendance_summary=summary)

@app.route("/attendance/refresh/<event_date>")
def attendance_refresh(event_date):
    """Return updated attendance table + summary (for AJAX auto-refresh)"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT a.student_id, s.name, a.status FROM attendance a JOIN students s ON a.student_id = s.id WHERE event_date = ?", (event_date,))
    attendance_records = c.fetchall()

    c.execute("SELECT COUNT(*), SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END), SUM(CASE WHEN status='Absent' THEN 1 ELSE 0 END) FROM attendance WHERE event_date = ?", (event_date,))
    total, present, absent = c.fetchone()
    conn.close()

    table_html = render_template("attendance_table.html", attendance_records=attendance_records)

    return jsonify({
        "summary": {"total": total or 0, "present": present or 0, "absent": absent or 0},
        "table_html": table_html
    })

# ---------------- SEARCH ----------------
@app.route("/search", methods=["GET", "POST"])
def search():
    # Fetch all student names for autocomplete
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT name FROM students ORDER BY name")
    all_names = [row[0] for row in c.fetchall()]
    conn.close()

    student = None

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        ieee_id = request.form.get("ieee_id", "").strip()
        captcha_answer = request.form.get("captcha_answer", "").strip()

        # Read CAPTCHA numbers from hidden inputs
        try:
            num1 = int(request.form.get("num1", 0))
            num2 = int(request.form.get("num2", 0))
        except ValueError:
            num1, num2 = 0, 0

        # Validate CAPTCHA
        if not captcha_answer.isdigit() or int(captcha_answer) != (num1 + num2):
            flash("❌ Incorrect CAPTCHA. Please try again.", "danger")
            # Generate new random numbers for next attempt
            num1, num2 = random.randint(1, 5), random.randint(1, 5)
            return render_template(
                "search.html",
                all_student_names=all_names,
                num1=num1, num2=num2,
                student=None
            )

        # Search query
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        if ieee_id:
            c.execute("SELECT name, ieee_id FROM students WHERE ieee_id = ?", (ieee_id,))
        else:
            c.execute("SELECT name, ieee_id FROM students WHERE name LIKE ?", (f"%{name}%",))
        row = c.fetchone()
        conn.close()

        if row:
            student = {
                "name": row[0],
                "ieee_id": row[1],
                "history": {
                    "total_downloads": random.randint(1, 10),
                    "last_login": "2025-09-10",
                    "recent_searches": "AI, ML, Robotics"
                }
            }
        else:
            flash("⚠️ No student record found.", "warning")
            # Generate new CAPTCHA for next attempt
            num1, num2 = random.randint(1, 5), random.randint(1, 5)

    else:
        # For GET requests, generate initial CAPTCHA numbers
        num1, num2 = random.randint(1, 5), random.randint(1, 5)

    return render_template(
        "search.html",
        all_student_names=all_names,
        num1=num1, num2=num2,
        student=student
    )

@app.route("/admin/get_stats")
def get_stats():
    """Return JSON stats for AJAX calls in dashboard"""
    conn = sqlite3.connect(DATABASE)
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

    conn.close()

    stats = {
        "total_students": total_students,
        "tech": tech,
        "non_tech": non_tech,
        **society_counts
    }
    return jsonify(stats)
@app.route("/admin/get_attendance_reports")
def get_attendance_reports():
    """Return list of attendance report files for dashboard AJAX"""
    attendance_files = os.listdir('static/attendance_reports') if os.path.exists('static/attendance_reports') else []
    return jsonify({"attendance_files": attendance_files})
    
