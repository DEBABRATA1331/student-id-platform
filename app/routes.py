from flask import render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify, send_file
from app import app
import os
import pandas as pd
import random
import sqlite3
from app.models import clear_and_insert_students
# NOTE: Assuming generate_qr_code, generate_idcard_pdf, and generate_attendance_pdf exist in app.utils
from app.utils import generate_qr_code, generate_idcard_pdf 
import threading
import io
import csv
import datetime

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

    active_event_date = sorted(active_attendance.keys())[-1] if active_attendance else None

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
        search_results = [{"id": r[0], "name": r[1], "domain": r[2], "ieee_id": r[3]} for r in c.fetchall()]

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

        c.execute(
            "SELECT a.student_id, s.name, a.status FROM attendance a JOIN students s ON a.student_id = s.id WHERE event_date = ?",
            (event_date,)
        )
        records = c.fetchall()

        c.execute(
            "SELECT COUNT(*), SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END), SUM(CASE WHEN status='Absent' THEN 1 ELSE 0 END) FROM attendance WHERE event_date = ?",
            (event_date,)
        )
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

    c.execute(
        "SELECT a.student_id, s.name, a.status FROM attendance a JOIN students s ON a.student_id = s.id WHERE event_date = ?",
        (event_date,)
    )
    attendance_records = c.fetchall()

    c.execute(
        "SELECT COUNT(*), SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END), SUM(CASE WHEN status='Absent' THEN 1 ELSE 0 END) FROM attendance WHERE event_date = ?",
        (event_date,)
    )
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

    c.execute(
        "SELECT a.student_id, s.name, a.status FROM attendance a JOIN students s ON a.student_id = s.id WHERE event_date = ?",
        (event_date,)
    )
    attendance_records = c.fetchall()

    c.execute(
        "SELECT COUNT(*), SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END), SUM(CASE WHEN status='Absent' THEN 1 ELSE 0 END) FROM attendance WHERE event_date = ?",
        (event_date,)
    )
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
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT name FROM students ORDER BY name")
    all_names = [row[0] for row in c.fetchall()]
    conn.close()

    # Generate CAPTCHA numbers
    if "captcha_num1" not in session or "captcha_num2" not in session:
        session["captcha_num1"] = random.randint(1, 5)
        session["captcha_num2"] = random.randint(1, 5)

    num1 = session["captcha_num1"]
    num2 = session["captcha_num2"]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        ieee_id = request.form.get("ieee_id", "").strip()
        captcha_answer = request.form.get("captcha_answer", "").strip()

        # Validate CAPTCHA
        if not captcha_answer.isdigit() or int(captcha_answer) != (num1 + num2):
            flash("❌ Incorrect CAPTCHA. Please try again.", "danger")
            session["captcha_num1"] = random.randint(1, 5)
            session["captcha_num2"] = random.randint(1, 5)
            return render_template(
                "search.html",
                all_student_names=all_names,
                num1=session["captcha_num1"],
                num2=session["captcha_num2"],
                student=None
            )

        # Search student
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        if ieee_id:
            c.execute("SELECT id, name, ieee_id, Domain, [Joining_Date], Category, qr_code FROM students WHERE ieee_id = ?", (ieee_id,))
        else:
            c.execute("SELECT id, name, ieee_id, Domain, [Joining_Date], Category, qr_code FROM students WHERE name LIKE ?", (f"%{name}%",))
        row = c.fetchone()
        conn.close()

        if row:
            # FIX APPLIED HERE: Robustly decode qr_code from bytes (row[6]) to string
            qr_code_value = row[6]
            
            if isinstance(qr_code_value, bytes):
                try:
                    # Try standard UTF-8 decoding first
                    qr_code_value = qr_code_value.decode('utf-8')
                except UnicodeDecodeError:
                    # If UTF-8 fails (as with the 0x89 byte), fall back to latin-1,
                    # which can decode all byte values and usually works for file paths.
                    qr_code_value = qr_code_value.decode('latin-1')

            student = {
                "id": row[0],
                "name": row[1],
                "ieee_id": row[2],
                "domain": row[3],
                "joining_date": row[4],
                "category": row[5],
                "qr_code": qr_code_value, # Use the robustly decoded string value
                "download_count": random.randint(1, 10)
            }
            session["captcha_num1"] = random.randint(1, 5)
            session["captcha_num2"] = random.randint(1, 5)
            return render_template("idcard.html", student=student)
        else:
            flash("⚠️ No student record found.", "warning")
            session["captcha_num1"] = random.randint(1, 5)
            session["captcha_num2"] = random.randint(1, 5)

    return render_template(
        "search.html",
        all_student_names=all_names,
        num1=num1,
        num2=num2,
        student=None
    )

# ---------------- ADMIN AJAX STATS ----------------
@app.route("/admin/get_stats")
def get_stats():
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
    attendance_files = os.listdir('static/attendance_reports') if os.path.exists('static/attendance_reports') else []
    return jsonify({"attendance_files": attendance_files})

# Note: The original request had `from flask import send_file` here, moved to the top.
@app.route("/download/<int:student_id>")
def user_download(student_id):
    conn = sqlite3.connect("instance/students.db")
    c = conn.cursor()
    c.execute("SELECT * FROM students WHERE id = ?", (student_id,))
    student = c.fetchone()
    conn.close()

    if not student:
        flash("Student not found", "danger")
        return redirect(url_for("search"))

    # Generate PDF
    pdf_bytes = generate_idcard_pdf(student)
    
    return send_file(
        io.BytesIO(pdf_bytes),
        as_attachment=True,
        download_name=f"idcard_{student[1]}.pdf",
        mimetype="application/pdf"
    )

@app.route("/attendance/")
def attendance_page():
    event_date = request.args.get("event_date")

    if not event_date:
        return "❌ Please provide ?event_date=YYYY-MM-DD", 400

    # get active session info (from in-memory dict)
    active_session = active_attendance.get(event_date)  # may be None
    now = datetime.datetime.now()

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Fetch all students
    cursor.execute("SELECT id, name FROM students")
    students = cursor.fetchall()

    # Fetch attendance records
    cursor.execute("""
        SELECT a.student_id, s.name, a.status
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        WHERE a.event_date = ?
    """, (event_date,))
    attendance_records = cursor.fetchall()

    # Attendance summary
    cursor.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END),
               SUM(CASE WHEN status='Absent' THEN 1 ELSE 0 END)
        FROM attendance WHERE event_date = ?
    """, (event_date,))
    row = cursor.fetchone() or (0, 0, 0)
    total, present, absent = row

    conn.close()

    attendance_summary = {
        "total": total or 0,
        "present": present or 0,
        "absent": absent or 0,
    }

    return render_template(
        "attendance.html",
        students=students,
        event_date=event_date,
        attendance_records=attendance_records,
        attendance_summary=attendance_summary,
        active_session=active_session,  # <-- added
        now=now                        # <-- added
    )


@app.route("/attendance/mark/<event_date>", methods=["POST"])
def mark_attendance(event_date):
    student_id = request.form.get("student_id")
    status = request.form.get("status")

    if not student_id or not status:
        return jsonify({"error": "Missing data"}), 400

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Insert or update attendance
    cursor.execute("""
        INSERT INTO attendance (student_id, event_date, status)
        VALUES (?, ?, ?)
        ON CONFLICT(student_id, event_date) DO UPDATE SET status=excluded.status
    """, (student_id, event_date, status))

    conn.commit()

    # Fetch updated records
    cursor.execute("""
        SELECT a.student_id, s.name, a.status
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        WHERE a.event_date = ?
    """, (event_date,))
    attendance_records = cursor.fetchall()

    # Fetch updated summary
    cursor.execute("""
        SELECT COUNT(*), 
               SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END), 
               SUM(CASE WHEN status='Absent' THEN 1 ELSE 0 END) 
        FROM attendance WHERE event_date = ?
    """, (event_date,))
    total, present, absent = cursor.fetchone() or (0, 0, 0)

    conn.close()

    # Render partial table
    table_html = render_template("attendance_table.html", attendance_records=attendance_records)

    return jsonify({
        "summary": {"total": total, "present": present, "absent": absent},
        "table_html": table_html
    })

@app.route("/attendance/start", methods=["POST"])
def start_attendance_session():
    event_date = request.form.get("event_date")
    if not event_date:
        flash("Event date is required", "danger")
        return redirect(url_for("admin_dashboard"))

    # Session expires after 3 min
    expiry_time = datetime.datetime.now() + datetime.timedelta(minutes=3)
    active_attendance[event_date] = {"expires": expiry_time}

    flash(f"Attendance session started for {event_date} (valid 3 min)", "success")
    return redirect(url_for("attendance_page", event_date=event_date))

@app.route("/attendance/self_mark/<event_date>", methods=["POST"])
def student_self_mark(event_date):
    student_id = request.form.get("student_id")

    # ✅ check if session active
    session_info = active_attendance.get(event_date)
    if not session_info or session_info["expires"] < datetime.datetime.now():
        flash("❌ Attendance session expired or not active.", "danger")
        return redirect(url_for("attendance_page", event_date=event_date))
        return redirect(url_for("home"))

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO attendance (student_id, event_date, status)
        VALUES (?, ?, 'Present')
        ON CONFLICT(student_id, event_date) DO UPDATE SET status='Present'
    """, (student_id, event_date))

    conn.commit()
    conn.close()

    flash("✅ Attendance marked successfully!", "success")
    return redirect(url_for("home"))

@app.route("/attendance/manual_add/<event_date>", methods=["POST"])
def admin_manual_add(event_date):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    student_id = request.form.get("student_id")
    status = request.form.get("status", "Present")

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO attendance (student_id, event_date, status)
        VALUES (?, ?, ?)
        ON CONFLICT(student_id, event_date) DO UPDATE SET status=excluded.status
    """, (student_id, event_date, status))

    conn.commit()
    conn.close()

    flash("✅ Student added manually.", "success")
    return redirect(url_for("attendance_page", event_date=event_date))


@app.route("/attendance/report/<event_date>")
def attendance_report(event_date):
    # Note: Assumes generate_attendance_pdf is available.
    # You will need to import generate_attendance_pdf if you use this route.
    # If it's in app.utils, ensure it's imported correctly.
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.id, s.name, a.status, a.marked_by
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        WHERE a.event_date = ?
    """, (event_date,))
    records = cursor.fetchall()
    conn.close()

    # NOTE: You need to ensure 'generate_attendance_pdf' is available in app.utils 
    # and handles the data correctly.
    # pdf_bytes = generate_attendance_pdf(records, event_date)  # <-- Uncomment and ensure this function is defined
    
    # Placeholder for generate_attendance_pdf call
    # You must define/import 'generate_attendance_pdf' elsewhere.
    try:
        from app.utils import generate_attendance_pdf
        pdf_bytes = generate_attendance_pdf(records, event_date)
    except ImportError:
        # Fallback if the utility function is missing. 
        # This will need to be fixed in your project.
        flash("PDF generation function missing!", "danger")
        return redirect(url_for("admin_dashboard"))
    except NameError:
        # Fallback if the function is not in scope
        flash("PDF generation function not found!", "danger")
        return redirect(url_for("admin_dashboard"))
    
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"Attendance_{event_date}.pdf"
    )