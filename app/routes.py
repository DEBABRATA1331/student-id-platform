from flask import render_template, request, redirect, url_for, session, flash, send_from_directory
from app import app
import os
import pandas as pd
import random
import sqlite3
from app.models import clear_and_insert_students
from app.utils import generate_qr_code, generate_idcard_pdf

# ---------------- CONFIG ----------------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


# ---------------- HOME ----------------
@app.route('/')
def home():
    admin_manual = os.path.exists(os.path.join(app.static_folder, "admin_manual.pdf"))
    student_manual = os.path.exists(os.path.join(app.static_folder, "student_manual.pdf"))
    return render_template("home.html", admin_manual=admin_manual, student_manual=student_manual)


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

    return render_template("dashboard.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    flash("Logged out successfully!", "info")
    return redirect(url_for("admin_login"))


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
        return send_from_directory("app/static/qrcodes", pdf_file, as_attachment=True)
    else:
        flash("⚠ Student not found!", "warning")
        return redirect(url_for("user_search"))
