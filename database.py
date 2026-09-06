import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "healthconnect.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(seed=True):
    """Create tables fresh and optionally seed demo data."""
    conn = get_db()
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    conn.commit()
    if seed:
        _seed(conn)
    conn.close()


def _seed(conn):
    from werkzeug.security import generate_password_hash

    cur = conn.cursor()

    # --- Doctors ---
    doctors = [
        ("Dr. Ananya Rao", "ananya.rao@healthconnect.io", "9876500001", "Cardiologist",
         12, "Sunrise Multispecialty Hospital", 4.8, 800,
         "Focuses on preventive cardiology and long-term heart health.", 3),
        ("Dr. Vikram Shah", "vikram.shah@healthconnect.io", "9876500002", "Dermatologist",
         8, "CityCare Clinic", 4.6, 600,
         "Treats chronic skin conditions and cosmetic dermatology.", 2),
        ("Dr. Meera Iyer", "meera.iyer@healthconnect.io", "9876500003", "Pediatrician",
         15, "Little Sparrows Children's Hospital", 4.9, 500,
         "Specialises in newborn and adolescent care.", 5),
        ("Dr. Arjun Nair", "arjun.nair@healthconnect.io", "9876500004", "Orthopedic",
         10, "Sunrise Multispecialty Hospital", 4.5, 700,
         "Sports injuries, joint replacement and physiotherapy guidance.", 1),
    ]
    doctor_ids = []
    availability_flags = [1, 1, 0, 1]  # Dr. Meera Iyer starts offline, for demo purposes
    for (name, email, phone, spec, exp, hosp, rating, fee, bio, appts), is_avail in zip(doctors, availability_flags):
        cur.execute(
            """INSERT INTO users (name, email, passwordHash, phone, role, isActive)
               VALUES (?, ?, ?, ?, 'doctor', 1)""",
            (name, email, generate_password_hash("password123"), phone),
        )
        uid = cur.lastrowid
        cur.execute(
            """INSERT INTO doctors (doctorId, specialization, experience, hospitalName,
                                     rating, consultationFee, bio, totalAppointments, isAvailable)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, spec, exp, hosp, rating, fee, bio, appts, is_avail),
        )
        doctor_ids.append(uid)

    availability = [
        (doctor_ids[0], "Monday", "09:00", "13:00"),
        (doctor_ids[0], "Wednesday", "09:00", "13:00"),
        (doctor_ids[0], "Friday", "14:00", "18:00"),
        (doctor_ids[1], "Tuesday", "10:00", "16:00"),
        (doctor_ids[1], "Thursday", "10:00", "16:00"),
        (doctor_ids[2], "Monday", "11:00", "17:00"),
        (doctor_ids[2], "Tuesday", "11:00", "17:00"),
        (doctor_ids[2], "Saturday", "09:00", "12:00"),
        (doctor_ids[3], "Wednesday", "12:00", "18:00"),
        (doctor_ids[3], "Friday", "09:00", "12:00"),
    ]
    cur.executemany(
        "INSERT INTO doctor_availability (doctorId, day, startTime, endTime) VALUES (?,?,?,?)",
        availability,
    )

    # --- Demo patient ---
    cur.execute(
        """INSERT INTO users (name, email, passwordHash, phone, role, isActive)
           VALUES (?, ?, ?, ?, 'patient', 1)""",
        ("Rahul Verma", "rahul.verma@example.com", generate_password_hash("password123"), "9876512345"),
    )
    pid = cur.lastrowid
    cur.execute(
        """INSERT INTO patients (patientId, gender, dateOfBirth, bloodGroup, height, weight,
                                  allergies, chronicDiseases, emergencyContactName,
                                  emergencyContactPhone, city, state, pincode)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (pid, "Male", "1994-03-12", "O+", 175, 72, "Pollen", "None",
         "Sunita Verma", "9876554321", "Visakhapatnam", "Andhra Pradesh", "530001"),
    )

    # A sample appointment + record so the dashboard isn't empty
    cur.execute(
        """INSERT INTO appointments (patientId, doctorId, appointmentDate, slot, mode, status, paymentStatus)
           VALUES (?, ?, date('now','+2 day'), '09:00-09:30', 'online', 'confirmed', 'paid')""",
        (pid, doctor_ids[0]),
    )
    appt_id = cur.lastrowid
    cur.execute(
        """INSERT INTO payments (appointmentId, patientId, doctorId, amount, paymentMethod, transactionId, status)
           VALUES (?, ?, ?, ?, 'upi', 'TXN10001', 'success')""",
        (appt_id, pid, doctor_ids[0], 800),
    )
    cur.execute(
        """INSERT INTO medical_records (patientId, doctorId, diagnosis, prescription, notes, followUpDate)
           VALUES (?, ?, 'Seasonal allergy', 'Cetirizine 10mg, once daily',
                   'Advised to avoid dust exposure and follow up if symptoms persist.', date('now','+30 day'))""",
        (pid, doctor_ids[0]),
    )

    # AI chat for the demo patient
    import json
    cur.execute(
        "INSERT INTO chats (participants, chatType, aiEnabled, lastMessage, lastMessageTime) VALUES (?, 'ai', 1, ?, datetime('now'))",
        (json.dumps([pid]), "Hello! I'm your Aarogya Connect assistant."),
    )
    chat_id = cur.lastrowid
    cur.execute(
        """INSERT INTO messages (chatId, senderId, senderType, message, messageType)
           VALUES (?, NULL, 'ai', 'Hello! I''m your Aarogya Connect assistant. What symptom is bothering you today?', 'text')""",
        (chat_id,),
    )

    # --- Demo pharmacy: approved, and registered as Dr. Ananya Rao's own dispensary ---
    cur.execute(
        """INSERT INTO users (name, email, passwordHash, phone, role, isActive)
           VALUES (?, ?, ?, ?, 'pharmacy', 1)""",
        ("Sunrise Pharmacy", "sunrise.pharmacy@healthconnect.io",
         generate_password_hash("password123"), "9876500011"),
    )
    pharm_id = cur.lastrowid
    cur.execute(
        """INSERT INTO pharmacies (pharmacyId, pharmacyName, licenseNumber, address,
                                    ownerDoctorId, approverDoctorId, approvalStatus, approvedAt)
           VALUES (?, 'Sunrise Pharmacy', 'AP-PH-10234', 'Ground Floor, Sunrise Multispecialty Hospital, Visakhapatnam',
                   ?, ?, 'approved', datetime('now'))""",
        (pharm_id, doctor_ids[0], doctor_ids[0]),
    )

    # A second pharmacy still waiting on Dr. Ananya Rao's approval, for demo purposes
    cur.execute(
        """INSERT INTO users (name, email, passwordHash, phone, role, isActive)
           VALUES (?, ?, ?, ?, 'pharmacy', 1)""",
        ("CityCare Pharmacy", "citycare.pharmacy@healthconnect.io",
         generate_password_hash("password123"), "9876500012"),
    )
    pharm_id2 = cur.lastrowid
    cur.execute(
        """INSERT INTO pharmacies (pharmacyId, pharmacyName, licenseNumber, address,
                                    ownerDoctorId, approverDoctorId, approvalStatus)
           VALUES (?, 'CityCare Pharmacy', 'AP-PH-10877', 'MG Road, Visakhapatnam', NULL, ?, 'pending')""",
        (pharm_id2, doctor_ids[0]),
    )

    conn.commit()


if __name__ == "__main__":
    init_db(seed=True)
    print("Database initialised at", DB_PATH)
