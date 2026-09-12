import os
import json
import uuid
from datetime import datetime

from flask import Flask, request, session, redirect, url_for, render_template, jsonify, g, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from database import get_db, init_db, DB_PATH
from prescription import generate_prescription_image
from certificate_verify import verify_certificate

APP_ROOT = os.path.dirname(__file__)
UPLOAD_FOLDER = os.path.join(APP_ROOT, "static", "uploads")
CERTIFICATE_FOLDER = os.path.join(APP_ROOT, "static", "certificates")
ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

app = Flask(__name__)
app.secret_key = "healthconnect-dev-secret-change-me"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB

if not os.path.exists(DB_PATH):
    init_db(seed=True)


# ---------------------------------------------------------------- helpers --

def db():
    if "db" not in g:
        g.db = get_db()
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def current_user():
    uid = session.get("userId")
    if not uid:
        return None
    row = db().execute("SELECT * FROM users WHERE userId = ?", (uid,)).fetchone()
    return dict(row) if row else None


def login_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("userId"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Not authenticated"}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def row_to_dict(row):
    return dict(row) if row else None


def rows_to_list(rows):
    return [dict(r) for r in rows]


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXT


# ------------------------------------------------------------------ pages --

@app.route("/")
def index():
    if session.get("userId"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("userId"):
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = db().execute("SELECT * FROM users WHERE lower(email) = ?", (email,)).fetchone()
    if not user or not check_password_hash(user["passwordHash"], password):
        return jsonify({"error": "Invalid email or password"}), 401
    if not user["isActive"]:
        return jsonify({"error": "This account has been deactivated"}), 403

    if user["role"] == "pharmacy":
        pharmacy = db().execute("SELECT * FROM pharmacies WHERE pharmacyId=?", (user["userId"],)).fetchone()
        if pharmacy and pharmacy["approvalStatus"] == "pending":
            doc = db().execute(
                "SELECT u.name FROM doctors d JOIN users u ON u.userId=d.doctorId WHERE d.doctorId=?",
                (pharmacy["approverDoctorId"],),
            ).fetchone()
            doc_name = doc["name"] if doc else "the reviewing doctor"
            return jsonify({"error": f"Your pharmacy account is awaiting approval from {doc_name}."}), 403
        if pharmacy and pharmacy["approvalStatus"] == "rejected":
            return jsonify({"error": "Your pharmacy account request was not approved."}), 403

    session["userId"] = user["userId"]
    session["role"] = user["role"]
    return jsonify({"ok": True, "redirect": url_for("dashboard")})


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        if session.get("userId"):
            return redirect(url_for("dashboard"))
        return render_template("signup.html")

    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    phone = (data.get("phone") or "").strip()
    role = data.get("role") if data.get("role") in ("patient", "doctor", "pharmacy") else "patient"

    if not name or not email or len(password) < 6:
        return jsonify({"error": "Name, a valid email and a password (6+ chars) are required"}), 400

    if role == "pharmacy" and not data.get("approverDoctorId"):
        return jsonify({"error": "Select a doctor to request approval from"}), 400

    existing = db().execute("SELECT userId FROM users WHERE lower(email) = ?", (email,)).fetchone()
    if existing:
        return jsonify({"error": "An account with this email already exists"}), 409

    conn = db()
    cur = conn.execute(
        """INSERT INTO users (name, email, passwordHash, phone, role, isActive)
           VALUES (?, ?, ?, ?, ?, 1)""",
        (name, email, generate_password_hash(password), phone, role),
    )
    uid = cur.lastrowid

    if role == "patient":
        conn.execute(
            """INSERT INTO patients (patientId, gender, dateOfBirth, city, state, pincode)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (uid, data.get("gender", ""), data.get("dateOfBirth", ""),
             data.get("city", ""), data.get("state", ""), data.get("pincode", "")),
        )
    elif role == "doctor":
        conn.execute(
            """INSERT INTO doctors (doctorId, specialization, experience, hospitalName, consultationFee, bio, isAvailable)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (uid, data.get("specialization", "General Physician"),
             int(data.get("experience") or 0), data.get("hospitalName", ""),
             float(data.get("consultationFee") or 0), data.get("bio", "")),
        )
    else:  # pharmacy — needs a doctor's approval before it can sign in
        approver_id = int(data.get("approverDoctorId"))
        owner_id = approver_id if data.get("isOwnPharmacy") else None
        conn.execute(
            """INSERT INTO pharmacies (pharmacyId, pharmacyName, licenseNumber, address,
                                        ownerDoctorId, approverDoctorId, approvalStatus)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            (uid, data.get("pharmacyName", name), data.get("licenseNumber", ""),
             data.get("address", ""), owner_id, approver_id),
        )
        conn.commit()
        return jsonify({
            "ok": True,
            "pending": True,
            "message": "Account created — it will be active once the doctor you selected approves it.",
        })

    conn.commit()
    session["userId"] = uid
    session["role"] = role
    return jsonify({"ok": True, "redirect": url_for("dashboard")})


@app.route("/api/public/doctors")
def public_doctors():
    """Unauthenticated list used by the pharmacy signup form's doctor picker."""
    rows = db().execute(
        """SELECT u.userId AS doctorId, u.name, d.specialization
           FROM doctors d JOIN users u ON u.userId = d.doctorId
           WHERE u.isActive = 1 ORDER BY u.name"""
    ).fetchall()
    return jsonify(rows_to_list(rows))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    return render_template("dashboard.html", user=user)


# --------------------------------------------------------------- profile --

@app.route("/api/me")
@login_required
def api_me():
    user = current_user()
    user.pop("passwordHash", None)
    extra = {}
    if user["role"] == "patient":
        extra = row_to_dict(db().execute("SELECT * FROM patients WHERE patientId=?", (user["userId"],)).fetchone())
    elif user["role"] == "doctor":
        extra = row_to_dict(db().execute("SELECT * FROM doctors WHERE doctorId=?", (user["userId"],)).fetchone())
    else:
        extra = row_to_dict(db().execute("SELECT * FROM pharmacies WHERE pharmacyId=?", (user["userId"],)).fetchone())
    return jsonify({"user": user, "profile": extra})


@app.route("/api/profile/upload", methods=["POST"])
@login_required
def upload_profile_image():
    if "image" not in request.files:
        return jsonify({"error": "No image supplied"}), 400
    file = request.files["image"]
    if file.filename == "" or not allowed_file(file.filename):
        return jsonify({"error": "Unsupported file type"}), 400

    ext = file.filename.rsplit(".", 1)[1].lower()
    fname = f"{session['userId']}_{uuid.uuid4().hex[:8]}.{ext}"
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], secure_filename(fname)))

    rel_path = f"/static/uploads/{fname}"
    db().execute("UPDATE users SET profileImage=?, updatedAt=datetime('now') WHERE userId=?",
                 (rel_path, session["userId"]))
    db().commit()
    return jsonify({"ok": True, "profileImage": rel_path})


@app.route("/api/doctors/<int:doctor_id>/certificate", methods=["POST"])
@login_required
def upload_certificate(doctor_id):
    user = current_user()
    if user["role"] != "doctor" or user["userId"] != doctor_id:
        return jsonify({"error": "Forbidden"}), 403
    if "certificate" not in request.files:
        return jsonify({"error": "No certificate file supplied"}), 400
    file = request.files["certificate"]
    if file.filename == "" or not allowed_file(file.filename):
        return jsonify({"error": "Upload a PNG, JPG or WEBP image of the certificate"}), 400

    ext = file.filename.rsplit(".", 1)[1].lower()
    fname = f"cert_{doctor_id}_{uuid.uuid4().hex[:8]}.{ext}"
    os.makedirs(CERTIFICATE_FOLDER, exist_ok=True)
    fpath = os.path.join(CERTIFICATE_FOLDER, secure_filename(fname))
    file.save(fpath)
    rel_path = f"/static/certificates/{fname}"

    conn = db()
    conn.execute(
        """UPDATE doctors SET certificateImage=?, verificationStatus='pending',
                               verificationNotes='Scanning…', verifiedAt=NULL, updatedAt=datetime('now')
           WHERE doctorId=?""",
        (rel_path, doctor_id),
    )
    conn.commit()

    result = verify_certificate(fpath, user["name"])
    verified_at = "datetime('now')" if result["status"] in ("verified", "rejected") else "NULL"
    conn.execute(
        f"""UPDATE doctors SET verificationStatus=?, verificationNotes=?, verifiedAt={verified_at}, updatedAt=datetime('now')
            WHERE doctorId=?""",
        (result["status"], result["notes"], doctor_id),
    )
    conn.commit()

    return jsonify({
        "ok": True,
        "certificateImage": rel_path,
        "verificationStatus": result["status"],
        "verificationNotes": result["notes"],
    })


# -------------------------------------------------------------- patients --

@app.route("/api/patients")
@login_required
def api_patients():
    """Doctors get the full list; a patient only sees themself."""
    user = current_user()
    if user["role"] == "doctor":
        rows = db().execute(
            """SELECT u.userId, u.name, u.email, u.phone, u.profileImage, p.*
               FROM patients p JOIN users u ON u.userId = p.patientId
               ORDER BY u.name"""
        ).fetchall()
    else:
        rows = db().execute(
            """SELECT u.userId, u.name, u.email, u.phone, u.profileImage, p.*
               FROM patients p JOIN users u ON u.userId = p.patientId
               WHERE p.patientId = ?""",
            (user["userId"],),
        ).fetchall()
    return jsonify(rows_to_list(rows))


@app.route("/api/patients/<int:patient_id>", methods=["PUT"])
@login_required
def update_patient(patient_id):
    user = current_user()
    if user["role"] == "patient" and user["userId"] != patient_id:
        return jsonify({"error": "Forbidden"}), 403

    data = request.get_json(force=True)
    fields = ["gender", "dateOfBirth", "bloodGroup", "height", "weight", "allergies",
              "chronicDiseases", "emergencyContactName", "emergencyContactPhone",
              "city", "state", "pincode"]
    updates = {k: data[k] for k in fields if k in data}
    if not updates:
        return jsonify({"error": "Nothing to update"}), 400

    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [patient_id]
    db().execute(f"UPDATE patients SET {set_clause}, updatedAt=datetime('now') WHERE patientId=?", values)
    db().commit()
    return jsonify({"ok": True})


# --------------------------------------------------------------- doctors --

@app.route("/api/doctors")
@login_required
def api_doctors():
    rows = db().execute(
        """SELECT u.userId, u.name, u.email, u.phone, u.profileImage, d.*
           FROM doctors d JOIN users u ON u.userId = d.doctorId
           WHERE u.isActive = 1
           ORDER BY d.isAvailable DESC, d.rating DESC"""
    ).fetchall()
    doctors = rows_to_list(rows)
    for doc in doctors:
        slots = db().execute(
            "SELECT day, startTime, endTime FROM doctor_availability WHERE doctorId=? ORDER BY slotId",
            (doc["doctorId"],),
        ).fetchall()
        doc["availability"] = rows_to_list(slots)
    return jsonify(doctors)


@app.route("/api/doctors/<int:doctor_id>/status", methods=["PUT"])
@login_required
def set_doctor_status(doctor_id):
    user = current_user()
    if user["role"] != "doctor" or user["userId"] != doctor_id:
        return jsonify({"error": "Forbidden"}), 403
    data = request.get_json(force=True)
    is_available = 1 if data.get("isAvailable") else 0
    db().execute("UPDATE doctors SET isAvailable=?, updatedAt=datetime('now') WHERE doctorId=?",
                 (is_available, doctor_id))
    db().commit()
    return jsonify({"ok": True, "isAvailable": bool(is_available)})


@app.route("/api/doctors/<int:doctor_id>/availability", methods=["POST"])
@login_required
def set_availability(doctor_id):
    user = current_user()
    if user["role"] != "doctor" or user["userId"] != doctor_id:
        return jsonify({"error": "Forbidden"}), 403
    data = request.get_json(force=True)
    day, start, end = data.get("day"), data.get("startTime"), data.get("endTime")
    if not (day and start and end):
        return jsonify({"error": "day, startTime and endTime are required"}), 400
    db().execute(
        "INSERT INTO doctor_availability (doctorId, day, startTime, endTime) VALUES (?,?,?,?)",
        (doctor_id, day, start, end),
    )
    db().commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------- appointments --

@app.route("/api/appointments", methods=["GET", "POST"])
@login_required
def api_appointments():
    user = current_user()
    conn = db()

    if request.method == "POST":
        data = request.get_json(force=True)
        if user["role"] != "patient":
            return jsonify({"error": "Only patients can book appointments"}), 403
        doctor_id = data.get("doctorId")
        date = data.get("appointmentDate")
        slot = data.get("slot", "")
        mode = data.get("mode", "online")
        if not doctor_id or not date:
            return jsonify({"error": "doctorId and appointmentDate are required"}), 400

        cur = conn.execute(
            """INSERT INTO appointments (patientId, doctorId, appointmentDate, slot, mode, status, paymentStatus)
               VALUES (?, ?, ?, ?, ?, 'pending', 'unpaid')""",
            (user["userId"], doctor_id, date, slot, mode),
        )
        conn.execute("UPDATE doctors SET totalAppointments = totalAppointments + 1 WHERE doctorId=?", (doctor_id,))
        conn.commit()
        return jsonify({"ok": True, "appointmentId": cur.lastrowid})

    if user["role"] == "patient":
        rows = conn.execute(
            """SELECT a.*, u.name AS doctorName, d.specialization, d.consultationFee
               FROM appointments a
               JOIN doctors d ON d.doctorId = a.doctorId
               JOIN users u ON u.userId = d.doctorId
               WHERE a.patientId=? ORDER BY a.appointmentDate DESC""",
            (user["userId"],),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT a.*, u.name AS patientName
               FROM appointments a
               JOIN users u ON u.userId = a.patientId
               WHERE a.doctorId=? ORDER BY a.appointmentDate DESC""",
            (user["userId"],),
        ).fetchall()
    return jsonify(rows_to_list(rows))


@app.route("/api/appointments/<int:appt_id>", methods=["PUT"])
@login_required
def update_appointment(appt_id):
    user = current_user()
    data = request.get_json(force=True)
    appt = db().execute("SELECT * FROM appointments WHERE appointmentId=?", (appt_id,)).fetchone()
    if not appt:
        return jsonify({"error": "Not found"}), 404
    if user["userId"] not in (appt["patientId"], appt["doctorId"]):
        return jsonify({"error": "Forbidden"}), 403

    allowed_fields = ["status", "cancellationReason", "meetingLink", "paymentStatus"]
    updates = {k: data[k] for k in allowed_fields if k in data}
    if not updates:
        return jsonify({"error": "Nothing to update"}), 400
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [appt_id]
    db().execute(f"UPDATE appointments SET {set_clause}, updatedAt=datetime('now') WHERE appointmentId=?", values)
    db().commit()
    return jsonify({"ok": True})


# ------------------------------------------------------------- payments --

@app.route("/api/payments", methods=["POST"])
@login_required
def create_payment():
    """Simulated payment — always succeeds unless the card number ends in 0000."""
    user = current_user()
    data = request.get_json(force=True)
    appt_id = data.get("appointmentId")
    method = data.get("paymentMethod", "upi")

    appt = db().execute("SELECT * FROM appointments WHERE appointmentId=?", (appt_id,)).fetchone()
    if not appt or appt["patientId"] != user["userId"]:
        return jsonify({"error": "Appointment not found"}), 404

    doctor = db().execute("SELECT consultationFee FROM doctors WHERE doctorId=?", (appt["doctorId"],)).fetchone()
    amount = doctor["consultationFee"]
    fake_card = str(data.get("cardNumber", ""))
    status = "failed" if fake_card.endswith("0000") and fake_card else "success"
    txn_id = f"TXN{uuid.uuid4().hex[:10].upper()}"

    conn = db()
    conn.execute(
        """INSERT INTO payments (appointmentId, patientId, doctorId, amount, paymentMethod, transactionId, status)
           VALUES (?,?,?,?,?,?,?)""",
        (appt_id, user["userId"], appt["doctorId"], amount, method, txn_id, status),
    )
    if status == "success":
        conn.execute(
            "UPDATE appointments SET paymentStatus='paid', status='confirmed', updatedAt=datetime('now') WHERE appointmentId=?",
            (appt_id,),
        )
    conn.commit()
    return jsonify({"ok": status == "success", "status": status, "transactionId": txn_id, "amount": amount})


@app.route("/api/payments")
@login_required
def list_payments():
    user = current_user()
    col = "patientId" if user["role"] == "patient" else "doctorId"
    rows = db().execute(f"SELECT * FROM payments WHERE {col}=? ORDER BY createdAt DESC", (user["userId"],)).fetchall()
    return jsonify(rows_to_list(rows))


# --------------------------------------------------------- medical records --

@app.route("/api/records", methods=["GET", "POST"])
@login_required
def api_records():
    user = current_user()
    conn = db()

    if request.method == "POST":
        if user["role"] != "doctor":
            return jsonify({"error": "Only doctors can add records"}), 403
        data = request.get_json(force=True)
        cur = conn.execute(
            """INSERT INTO medical_records (patientId, doctorId, diagnosis, prescription, notes, reportUrl, followUpDate)
               VALUES (?,?,?,?,?,?,?)""",
            (data.get("patientId"), user["userId"], data.get("diagnosis"), data.get("prescription"),
             data.get("notes"), data.get("reportUrl"), data.get("followUpDate")),
        )
        conn.commit()
        return jsonify({"ok": True, "recordId": cur.lastrowid})

    if user["role"] == "patient":
        rows = conn.execute(
            """SELECT r.*, u.name AS doctorName, d.specialization
               FROM medical_records r
               JOIN doctors d ON d.doctorId = r.doctorId
               JOIN users u ON u.userId = d.doctorId
               WHERE r.patientId=? ORDER BY r.createdAt DESC""",
            (user["userId"],),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT r.*, u.name AS patientName
               FROM medical_records r
               JOIN users u ON u.userId = r.patientId
               WHERE r.doctorId=? ORDER BY r.createdAt DESC""",
            (user["userId"],),
        ).fetchall()
    return jsonify(rows_to_list(rows))


# ------------------------------------------------------------------- chat --

AI_QUESTION_FLOW = [
    "What symptom is bothering you the most right now?",
    "How long have you had this symptom — hours, days, or longer?",
    "On a scale of 1–10, how severe would you say it is?",
    "Do you have any other symptoms alongside it, like fever, fatigue, or pain elsewhere?",
    "Have you taken any medication for it already?",
]

AI_KEYWORD_TIPS = {
    "chest pain": "Chest pain alongside shortness of breath can be serious — please consider an in-person visit soon.",
    "fever": "Stay hydrated and monitor your temperature. If it stays above 102°F for more than a day, see a doctor.",
    "headache": "Rest in a dim, quiet room and stay hydrated. Persistent or sudden severe headaches need medical review.",
    "rash": "Avoid scratching and note anything new you've eaten, worn, or touched recently.",
    "cough": "Keep track of whether it's dry or produces mucus — that detail helps the doctor a lot.",
}

# Keyword → specialization, used to suggest an available doctor mid-chat
SPECIALTY_MAP = {
    "chest pain": "Cardiologist", "heart": "Cardiologist", "palpitation": "Cardiologist",
    "rash": "Dermatologist", "skin": "Dermatologist", "acne": "Dermatologist",
    "child": "Pediatrician", "baby": "Pediatrician", "infant": "Pediatrician",
    "joint": "Orthopedic", "bone": "Orthopedic", "fracture": "Orthopedic", "sports injury": "Orthopedic",
    "fever": None, "headache": None, "cough": None,  # no clear specialist → fall back to top-rated available
}


def get_or_create_ai_chat(patient_id):
    conn = db()
    row = conn.execute(
        "SELECT * FROM chats WHERE chatType='ai' AND participants LIKE ?",
        (f'%{patient_id}%',),
    ).fetchone()
    if row:
        return dict(row)
    cur = conn.execute(
        "INSERT INTO chats (participants, chatType, aiEnabled, lastMessage, lastMessageTime) VALUES (?, 'ai', 1, ?, datetime('now'))",
        (json.dumps([patient_id]), "Hello! I'm your Aarogya Connect assistant."),
    )
    chat_id = cur.lastrowid
    conn.execute(
        """INSERT INTO messages (chatId, senderId, senderType, message, messageType)
           VALUES (?, NULL, 'ai', ?, 'text')""",
        (chat_id, "Hello! I'm your Aarogya Connect assistant. " + AI_QUESTION_FLOW[0]),
    )
    conn.commit()
    return {"chatId": chat_id}


def find_doctor_chat(patient_id, doctor_id):
    conn = db()
    rows = conn.execute("SELECT * FROM chats WHERE chatType='doctor'").fetchall()
    for r in rows:
        parts = json.loads(r["participants"])
        if patient_id in parts and doctor_id in parts:
            return dict(r)
    return None


def get_or_create_doctor_chat(patient_id, doctor_id):
    existing = find_doctor_chat(patient_id, doctor_id)
    if existing:
        return existing
    conn = db()
    cur = conn.execute(
        "INSERT INTO chats (participants, chatType, aiEnabled, lastMessage, lastMessageTime) VALUES (?, 'doctor', 0, NULL, datetime('now'))",
        (json.dumps([patient_id, doctor_id]),),
    )
    conn.commit()
    return {"chatId": cur.lastrowid}


def suggest_available_doctors(specialization=None, exclude_doctor_id=None, limit=3):
    conn = db()
    if specialization:
        rows = conn.execute(
            """SELECT u.userId AS doctorId, u.name, d.specialization, d.hospitalName,
                      d.rating, d.consultationFee, d.isAvailable
               FROM doctors d JOIN users u ON u.userId=d.doctorId
               WHERE u.isActive=1 AND d.isAvailable=1 AND d.specialization=?
               ORDER BY d.rating DESC LIMIT ?""",
            (specialization, limit),
        ).fetchall()
        if rows:
            return rows_to_list(rows)
    # fallback: top-rated available doctors of any specialization
    rows = conn.execute(
        """SELECT u.userId AS doctorId, u.name, d.specialization, d.hospitalName,
                  d.rating, d.consultationFee, d.isAvailable
           FROM doctors d JOIN users u ON u.userId=d.doctorId
           WHERE u.isActive=1 AND d.isAvailable=1
           ORDER BY d.rating DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return rows_to_list(rows)


@app.route("/api/chat")
@login_required
def open_chat():
    """The patient's single AI-triage chat (floating assistant bubble)."""
    user = current_user()
    if user["role"] != "patient":
        return jsonify({"error": "Chat is available for patients"}), 403
    chat = get_or_create_ai_chat(user["userId"])
    messages = db().execute(
        "SELECT * FROM messages WHERE chatId=? ORDER BY messageId", (chat["chatId"],)
    ).fetchall()
    return jsonify({"chatId": chat["chatId"], "messages": rows_to_list(messages)})


@app.route("/api/chats")
@login_required
def list_chats():
    """Doctor↔patient conversation list, for the Messages panel (both roles)."""
    user = current_user()
    conn = db()
    rows = conn.execute("SELECT * FROM chats WHERE chatType='doctor' ORDER BY lastMessageTime DESC").fetchall()
    out = []
    for r in rows:
        parts = json.loads(r["participants"])
        if user["userId"] not in parts:
            continue
        other_id = next((p for p in parts if p != user["userId"]), None)
        other = conn.execute("SELECT name, profileImage FROM users WHERE userId=?", (other_id,)).fetchone()
        is_avail = None
        if user["role"] == "patient":
            doc = conn.execute("SELECT isAvailable FROM doctors WHERE doctorId=?", (other_id,)).fetchone()
            is_avail = bool(doc["isAvailable"]) if doc else None
        out.append({
            "chatId": r["chatId"], "otherUserId": other_id,
            "otherName": other["name"] if other else "Unknown",
            "otherImage": other["profileImage"] if other else None,
            "isAvailable": is_avail,
            "lastMessage": r["lastMessage"], "lastMessageTime": r["lastMessageTime"],
        })
    return jsonify(out)


@app.route("/api/chat/doctor/<int:doctor_id>", methods=["POST"])
@login_required
def start_doctor_chat(doctor_id):
    user = current_user()
    if user["role"] != "patient":
        return jsonify({"error": "Only patients can start a doctor chat"}), 403
    doctor = db().execute("SELECT * FROM doctors WHERE doctorId=?", (doctor_id,)).fetchone()
    if not doctor:
        return jsonify({"error": "Doctor not found"}), 404
    chat = get_or_create_doctor_chat(user["userId"], doctor_id)
    return jsonify({"chatId": chat["chatId"]})


@app.route("/api/chat/<int:chat_id>")
@login_required
def get_chat_messages(chat_id):
    user = current_user()
    conn = db()
    chat = conn.execute("SELECT * FROM chats WHERE chatId=?", (chat_id,)).fetchone()
    if not chat:
        return jsonify({"error": "Not found"}), 404
    parts = json.loads(chat["participants"])
    if user["userId"] not in parts:
        return jsonify({"error": "Forbidden"}), 403
    messages = conn.execute("SELECT * FROM messages WHERE chatId=? ORDER BY messageId", (chat_id,)).fetchall()
    return jsonify({"chatId": chat_id, "chatType": chat["chatType"], "messages": rows_to_list(messages)})


@app.route("/api/chat/<int:chat_id>/messages", methods=["POST"])
@login_required
def send_message(chat_id):
    user = current_user()
    data = request.get_json(force=True)
    text = (data.get("message") or "").strip()
    msg_type = data.get("messageType", "text")
    if not text:
        return jsonify({"error": "Message cannot be empty"}), 400

    conn = db()
    chat = conn.execute("SELECT * FROM chats WHERE chatId=?", (chat_id,)).fetchone()
    if not chat:
        return jsonify({"error": "Chat not found"}), 404
    parts = json.loads(chat["participants"])
    if user["userId"] not in parts:
        return jsonify({"error": "Forbidden"}), 403

    conn.execute(
        """INSERT INTO messages (chatId, senderId, senderType, message, messageType)
           VALUES (?, ?, ?, ?, ?)""",
        (chat_id, user["userId"], user["role"], text, msg_type),
    )
    conn.execute("UPDATE chats SET lastMessage=?, lastMessageTime=datetime('now') WHERE chatId=?", (text, chat_id))

    new_message_ids = []

    if chat["chatType"] == "doctor":
        # Plain relay between patient and doctor — no AI involvement.
        conn.commit()
        last = conn.execute("SELECT * FROM messages WHERE chatId=? ORDER BY messageId DESC LIMIT 1", (chat_id,)).fetchone()
        return jsonify({"ok": True, "messages": [dict(last)]})

    # --- AI triage chat ---
    asked = conn.execute(
        "SELECT COUNT(*) c FROM messages WHERE chatId=? AND senderType='ai' AND messageType='text'", (chat_id,)
    ).fetchone()["c"]

    reply_parts = []
    lowered = text.lower()
    matched_specialization = "__unmatched__"
    for keyword, spec in SPECIALTY_MAP.items():
        if keyword in lowered:
            matched_specialization = spec
            reply_parts.append(AI_KEYWORD_TIPS.get(keyword, ""))
            break

    if asked < len(AI_QUESTION_FLOW):
        reply_parts.append(AI_QUESTION_FLOW[asked])
    else:
        reply_parts.append(
            "Thanks for the details. I've noted this for your doctor to review before your appointment. "
            "Is there anything else you'd like to add?"
        )

    ai_reply = " ".join(p for p in reply_parts if p)
    conn.execute(
        """INSERT INTO messages (chatId, senderId, senderType, message, messageType)
           VALUES (?, NULL, 'ai', ?, 'text')""",
        (chat_id, ai_reply),
    )
    conn.execute("UPDATE chats SET lastMessage=?, lastMessageTime=datetime('now') WHERE chatId=?", (ai_reply, chat_id))

    # Suggest available doctors — once a symptom keyword matches, or once the
    # question flow has run its course — but only the first time per chat.
    already_suggested = conn.execute(
        "SELECT COUNT(*) c FROM messages WHERE chatId=? AND messageType='doctor_suggestion'", (chat_id,)
    ).fetchone()["c"]
    should_suggest = matched_specialization != "__unmatched__" or asked >= len(AI_QUESTION_FLOW) - 1
    if not already_suggested and should_suggest:
        spec = matched_specialization if matched_specialization != "__unmatched__" else None
        doctors = suggest_available_doctors(specialization=spec)
        if doctors:
            intro = (f"Based on what you've described, here are available "
                     f"{spec.lower() + 's' if spec else 'doctors'} you could talk to right now:")
            conn.execute(
                """INSERT INTO messages (chatId, senderId, senderType, message, messageType)
                   VALUES (?, NULL, 'ai', ?, 'text')""",
                (chat_id, intro),
            )
            conn.execute(
                """INSERT INTO messages (chatId, senderId, senderType, message, messageType)
                   VALUES (?, NULL, 'ai', ?, 'doctor_suggestion')""",
                (chat_id, json.dumps(doctors)),
            )

    conn.commit()
    rows = conn.execute(
        "SELECT * FROM messages WHERE chatId=? ORDER BY messageId DESC LIMIT 4", (chat_id,)
    ).fetchall()
    return jsonify({"ok": True, "messages": rows_to_list(list(reversed(rows)))})


# -------------------------------------------------------------- pharmacies --

@app.route("/api/pharmacies")
@login_required
def list_pharmacies():
    """Approved pharmacies — used when a doctor prescribes or a patient orders."""
    conn = db()
    only_mine = request.args.get("mine") == "1"
    user = current_user()
    if only_mine and user["role"] == "doctor":
        rows = conn.execute(
            "SELECT * FROM pharmacies WHERE approvalStatus='approved' AND ownerDoctorId=?",
            (user["userId"],),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM pharmacies WHERE approvalStatus='approved'").fetchall()
    return jsonify(rows_to_list(rows))


@app.route("/api/pharmacy/requests")
@login_required
def pharmacy_requests():
    user = current_user()
    if user["role"] != "doctor":
        return jsonify({"error": "Forbidden"}), 403
    rows = db().execute(
        """SELECT p.*, u.name, u.email, u.phone FROM pharmacies p
           JOIN users u ON u.userId = p.pharmacyId
           WHERE p.approverDoctorId=? AND p.approvalStatus='pending'
           ORDER BY p.createdAt DESC""",
        (user["userId"],),
    ).fetchall()
    return jsonify(rows_to_list(rows))


@app.route("/api/pharmacy/requests/<int:pharmacy_id>", methods=["PUT"])
@login_required
def review_pharmacy_request(pharmacy_id):
    user = current_user()
    if user["role"] != "doctor":
        return jsonify({"error": "Forbidden"}), 403
    pharmacy = db().execute("SELECT * FROM pharmacies WHERE pharmacyId=?", (pharmacy_id,)).fetchone()
    if not pharmacy or pharmacy["approverDoctorId"] != user["userId"]:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(force=True)
    status = "approved" if data.get("approve") else "rejected"
    db().execute(
        "UPDATE pharmacies SET approvalStatus=?, approvedAt=datetime('now') WHERE pharmacyId=?",
        (status, pharmacy_id),
    )
    db().commit()
    return jsonify({"ok": True, "approvalStatus": status})


# ------------------------------------------------------------ prescriptions --

@app.route("/api/prescriptions", methods=["GET", "POST"])
@login_required
def api_prescriptions():
    user = current_user()
    conn = db()

    if request.method == "POST":
        if user["role"] != "doctor":
            return jsonify({"error": "Only doctors can write prescriptions"}), 403
        data = request.get_json(force=True)
        patient_id = data.get("patientId")
        medicines = data.get("medicines") or []
        if not patient_id or not medicines:
            return jsonify({"error": "patientId and at least one medicine are required"}), 400

        doctor_row = conn.execute(
            """SELECT u.name, d.specialization, d.hospitalName
               FROM doctors d JOIN users u ON u.userId=d.doctorId WHERE d.doctorId=?""",
            (user["userId"],),
        ).fetchone()
        patient_row = conn.execute(
            """SELECT u.name, p.gender, p.dateOfBirth
               FROM patients p JOIN users u ON u.userId=p.patientId WHERE p.patientId=?""",
            (patient_id,),
        ).fetchone()
        if not patient_row:
            return jsonify({"error": "Patient not found"}), 404

        pharmacy_id = data.get("pharmacyId")
        pharmacy_row = None
        if pharmacy_id:
            pharmacy_row = conn.execute("SELECT * FROM pharmacies WHERE pharmacyId=?", (pharmacy_id,)).fetchone()

        cur = conn.execute(
            """INSERT INTO prescriptions (recordId, patientId, doctorId, medicines, notes, suggestedPharmacyId)
               VALUES (?,?,?,?,?,?)""",
            (data.get("recordId"), patient_id, user["userId"], json.dumps(medicines),
             data.get("notes", ""), pharmacy_id),
        )
        prescription_id = cur.lastrowid

        image_path = generate_prescription_image(
            prescription_id,
            doctor=dict(doctor_row),
            patient=dict(patient_row),
            medicines=medicines,
            notes=data.get("notes", ""),
            pharmacy=dict(pharmacy_row) if pharmacy_row else None,
        )
        conn.execute("UPDATE prescriptions SET imagePath=? WHERE prescriptionId=?", (image_path, prescription_id))
        conn.commit()
        return jsonify({"ok": True, "prescriptionId": prescription_id, "imagePath": image_path})

    if user["role"] == "patient":
        rows = conn.execute(
            """SELECT rx.*, u.name AS doctorName, d.specialization, d.hospitalName
               FROM prescriptions rx
               JOIN doctors d ON d.doctorId = rx.doctorId
               JOIN users u ON u.userId = d.doctorId
               WHERE rx.patientId=? ORDER BY rx.createdAt DESC""",
            (user["userId"],),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT rx.*, u.name AS patientName
               FROM prescriptions rx
               JOIN users u ON u.userId = rx.patientId
               WHERE rx.doctorId=? ORDER BY rx.createdAt DESC""",
            (user["userId"],),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["medicines"] = json.loads(d["medicines"]) if d.get("medicines") else []
        result.append(d)
    return jsonify(result)


@app.route("/api/prescriptions/<int:prescription_id>/order", methods=["POST"])
@login_required
def order_prescription(prescription_id):
    user = current_user()
    if user["role"] != "patient":
        return jsonify({"error": "Only patients can place a pharmacy order"}), 403
    data = request.get_json(force=True)
    pharmacy_id = data.get("pharmacyId")

    conn = db()
    rx = conn.execute("SELECT * FROM prescriptions WHERE prescriptionId=?", (prescription_id,)).fetchone()
    if not rx or rx["patientId"] != user["userId"]:
        return jsonify({"error": "Prescription not found"}), 404
    pharmacy = conn.execute(
        "SELECT * FROM pharmacies WHERE pharmacyId=? AND approvalStatus='approved'", (pharmacy_id,)
    ).fetchone()
    if not pharmacy:
        return jsonify({"error": "Select a valid, approved pharmacy"}), 400

    cur = conn.execute(
        "INSERT INTO prescription_orders (prescriptionId, patientId, pharmacyId, status) VALUES (?,?,?,'placed')",
        (prescription_id, user["userId"], pharmacy_id),
    )
    conn.commit()
    return jsonify({"ok": True, "orderId": cur.lastrowid})


@app.route("/api/orders")
@login_required
def list_orders():
    user = current_user()
    conn = db()
    if user["role"] == "pharmacy":
        rows = conn.execute(
            """SELECT o.*, u.name AS patientName, rx.medicines, rx.imagePath
               FROM prescription_orders o
               JOIN users u ON u.userId = o.patientId
               JOIN prescriptions rx ON rx.prescriptionId = o.prescriptionId
               WHERE o.pharmacyId=? ORDER BY o.createdAt DESC""",
            (user["userId"],),
        ).fetchall()
    elif user["role"] == "patient":
        rows = conn.execute(
            """SELECT o.*, ph.pharmacyName, rx.medicines, rx.imagePath
               FROM prescription_orders o
               JOIN pharmacies ph ON ph.pharmacyId = o.pharmacyId
               JOIN prescriptions rx ON rx.prescriptionId = o.prescriptionId
               WHERE o.patientId=? ORDER BY o.createdAt DESC""",
            (user["userId"],),
        ).fetchall()
    else:
        return jsonify([])
    result = []
    for r in rows:
        d = dict(r)
        d["medicines"] = json.loads(d["medicines"]) if d.get("medicines") else []
        result.append(d)
    return jsonify(result)


@app.route("/api/orders/<int:order_id>", methods=["PUT"])
@login_required
def update_order(order_id):
    user = current_user()
    if user["role"] != "pharmacy":
        return jsonify({"error": "Forbidden"}), 403
    order = db().execute("SELECT * FROM prescription_orders WHERE orderId=?", (order_id,)).fetchone()
    if not order or order["pharmacyId"] != user["userId"]:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(force=True)
    status = data.get("status")
    if status not in ("processing", "ready", "fulfilled", "cancelled"):
        return jsonify({"error": "Invalid status"}), 400
    db().execute("UPDATE prescription_orders SET status=?, updatedAt=datetime('now') WHERE orderId=?", (status, order_id))
    db().commit()
    return jsonify({"ok": True})


# ------------------------------------------------------------------- main --

if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

if __name__ == "__main__":
    app.run(debug=True)
