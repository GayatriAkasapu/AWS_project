# Extended Flask App for MedTrack
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import uuid
from functools import wraps
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default_secret_key")

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# ---------- Logging Setup ----------
# logging.basicConfig(
#     filename='app.log',
#     level=logging.INFO,
#     format='%(asctime)s %(levelname)s: %(message)s',
#     datefmt='%Y-%m-%d %H:%M:%S'
# )

# ---------- In-Memory Storage ----------
users = []                 # List of user dicts
appointments = []         # List of appointment dicts

# ---------- Helper: Send Email ----------
def send_email(to_email, subject, message):
    from_email = os.getenv("SMTP_EMAIL")
    password = os.getenv("SMTP_PASSWORD")

    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(message, 'html'))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(from_email, password)
            server.send_message(msg)
        logging.info(f"Email sent to {to_email}")
    except Exception as e:
        logging.error(f"Email failed to send: {e}")

# ---------- Routes ----------

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        user_type = request.form.get('userType')
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not all([user_type, name, email, password, confirm_password]):
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for('signup'))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for('signup'))

        if any(u['email'] == email for u in users):
            flash("Email already registered.", "danger")
            return redirect(url_for('signup'))

        user = {
            'id': str(uuid.uuid4()),
            'type': user_type,
            'name': name,
            'email': email,
            'password': generate_password_hash(password)
        }

        if user_type == 'patient':
            user.update({
                'age': request.form.get('patient_age'),
                'address': request.form.get('address'),
                'mobile': request.form.get('mobile')
            })
        elif user_type == 'doctor':
            user.update({
                'age': request.form.get('doctor_age'),
                'specialization': request.form.get('specialization'),
                'mobile': request.form.get('mobile')
            })

        users.append(user)
        flash("Signup successful. Please log in.", "success")
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = request.form.get('role')
        email = request.form.get('email')
        password = request.form.get('password')

        user = next((u for u in users if u['email'] == email and u['type'] == role), None)

        if user and check_password_hash(user['password'], password):
            session['user'] = user['email']
            session['role'] = user['type']
            flash("Login successful!", "success")
            return redirect(url_for(f"{role}_dashboard"))

        flash("Invalid credentials or role mismatch.", "danger")
        return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for('login'))

@app.route('/patient/dashboard')
def patient_dashboard():
    if 'user' not in session or session.get('role') != 'patient':
        flash("Please log in as a patient.", "danger")
        return redirect(url_for('login'))

    user = next((u for u in users if u['email'] == session['user']), None)
    user_appointments = [a for a in appointments if a['patient_email'] == user['email']]

    pending = sum(1 for a in user_appointments if a['status'] == 'Pending')
    completed = sum(1 for a in user_appointments if a['status'] == 'Completed')
    total = len(user_appointments)

    doctor_list = [i for i, u in enumerate(users) if u['type'] == 'doctor']

    return render_template('patient_dashboard.html', user=user, appointments=user_appointments, users=users, pending=pending, completed=completed, total=total, doctor_list=doctor_list)

@app.route('/doctor/dashboard')
def doctor_dashboard():
    if 'user' not in session or session.get('role') != 'doctor':
        flash("Please log in as a doctor.", "danger")
        return redirect(url_for('login'))

    user = next((u for u in users if u['email'] == session['user']), None)
    if not user:
        flash("Doctor not found.", "danger")
        return redirect(url_for('login'))

    doctor_id = next((i for i, u in enumerate(users) if u['email'] == user['email']), None)
    if doctor_id is None:
        flash("Doctor profile not found.", "danger")
        return redirect(url_for('login'))

    doctor_appointments = [a for a in appointments if a['doctor_id'] == doctor_id]

    pending = sum(1 for a in doctor_appointments if a['status'] == 'Pending')
    completed = sum(1 for a in doctor_appointments if a['status'] == 'Completed')
    total = len(doctor_appointments)

    return render_template('doctor_dashboard.html', user=user, appointments=doctor_appointments, users=users, pending=pending, completed=completed, total=total)

@app.route('/book-appointment', methods=['GET', 'POST'])
def book_appointment():
    if 'user' not in session or session.get('role') != 'patient':
        flash("Please log in as a patient to book an appointment.", "danger")
        return redirect(url_for('login'))

    if request.method == 'POST':
        doctor_id = int(request.form.get('doctor_id'))
        date = request.form.get('appointment_date')
        time = request.form.get('appointment_time')
        symptoms = request.form.get('symptoms', '')

        appointment = {
            'appointment_id': str(uuid.uuid4()),
            'patient_email': session['user'],
            'doctor_id': doctor_id,
            'date': date,
            'time': time,
            'status': 'Pending',
            'symptoms': symptoms,
            'patient_id': next(i for i, u in enumerate(users) if u['email'] == session['user']),
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        appointments.append(appointment)

        doctor = users[doctor_id]
        subject = "New Appointment Booked"
        message = f"<h3>New Appointment</h3><p>You have a new appointment on {date} at {time}.<br>Symptoms: {symptoms}</p>"
        if 'email' in doctor:
            send_email(doctor['email'], subject, message)

        flash("Appointment booked successfully! Notification sent to doctor.", "success")
        return redirect(url_for('patient_dashboard'))

    doctor_dict = {i: u for i, u in enumerate(users) if u['type'] == 'doctor'}
    return render_template('book_appointment.html', doctors=doctor_dict)

@app.route('/view-appointment/<appointment_id>')
def view_appointment_patient(appointment_id):
    appt = next((a for a in appointments if a['appointment_id'] == appointment_id), None)
    if not appt or session.get('user') != appt['patient_email']:
        flash("Access denied.", "danger")
        return redirect(url_for('patient_dashboard'))

    doctor = users[appt['doctor_id']]
    return render_template("view_appointment_patient.html", appointment=appt, doctor=doctor)

@app.route('/doctor/view-appointment/<appointment_id>')
def view_appointment_doctor(appointment_id):
    appt = next((a for a in appointments if a['appointment_id'] == appointment_id), None)
    if not appt:
        flash("Appointment not found.", "danger")
        return redirect(url_for('doctor_dashboard'))

    patient = users[appt['patient_id']]
    return render_template("view_appointment_doctor.html", appointment=appt, patient=patient)

@app.route('/doctor/submit-diagnosis/<appointment_id>', methods=['POST'])
def submit_diagnosis(appointment_id):
    if 'user' not in session or session.get('role') != 'doctor':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('login'))

    diagnosis = request.form.get('diagnosis')
    treatment_plan = request.form.get('treatment_plan')
    prescription = request.form.get('prescription')

    for appt in appointments:
        if appt['appointment_id'] == appointment_id:
            appt['diagnosis'] = diagnosis
            appt['treatment_plan'] = treatment_plan
            appt['prescription'] = prescription
            appt['status'] = 'Completed'
            flash("Diagnosis submitted successfully.", "success")
            break
    else:
        flash("Appointment not found.", "danger")

    return redirect(url_for('doctor_dashboard'))

@app.route('/patient/profile')
def patient_profile():
    user = next((u for u in users if u['email'] == session.get('user')), None)
    if not user or session.get('role') != 'patient':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('login'))
    return render_template("patient_profile.html", user=user)

@app.route('/doctor/profile')
def doctor_profile():
    user = next((u for u in users if u['email'] == session.get('user')), None)
    if not user or session.get('role') != 'doctor':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('login'))
    return render_template("doctor_profile.html", user=user)

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = next((u for u in users if u['email'] == email), None)
        if user:
            flash("Password reset link sent (simulated).", "success")
        else:
            flash("Email not found.", "danger")
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

if __name__ == '__main__':
    app.run(debug=True)