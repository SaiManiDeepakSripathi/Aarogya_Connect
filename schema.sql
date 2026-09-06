-- Aarogya Connect database schema (SQLite)

DROP TABLE IF EXISTS prescription_orders;
DROP TABLE IF EXISTS prescriptions;
DROP TABLE IF EXISTS pharmacies;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS chats;
DROP TABLE IF EXISTS medical_records;
DROP TABLE IF EXISTS appointments;
DROP TABLE IF EXISTS doctor_availability;
DROP TABLE IF EXISTS doctors;
DROP TABLE IF EXISTS patients;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    userId          INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    passwordHash    TEXT NOT NULL,
    phone           TEXT,
    role            TEXT NOT NULL CHECK (role IN ('patient','doctor','pharmacy')),
    profileImage    TEXT,
    isActive        INTEGER NOT NULL DEFAULT 1,
    createdAt       TEXT NOT NULL DEFAULT (datetime('now')),
    updatedAt       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE patients (
    patientId               INTEGER PRIMARY KEY REFERENCES users(userId),
    gender                  TEXT,
    dateOfBirth              TEXT,
    bloodGroup               TEXT,
    height                    REAL,
    weight                    REAL,
    allergies                 TEXT,
    chronicDiseases           TEXT,
    emergencyContactName      TEXT,
    emergencyContactPhone     TEXT,
    city                      TEXT,
    state                     TEXT,
    pincode                   TEXT,
    createdAt                 TEXT NOT NULL DEFAULT (datetime('now')),
    updatedAt                 TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE doctors (
    doctorId          INTEGER PRIMARY KEY REFERENCES users(userId),
    specialization     TEXT,
    experience          INTEGER,
    hospitalName        TEXT,
    rating               REAL DEFAULT 4.5,
    consultationFee      REAL DEFAULT 0,
    bio                  TEXT,
    totalAppointments    INTEGER DEFAULT 0,
    isAvailable          INTEGER NOT NULL DEFAULT 1,
    certificateImage      TEXT,
    verificationStatus       TEXT NOT NULL CHECK (verificationStatus IN ('unverified','pending','verified','rejected')) DEFAULT 'unverified',
    verificationNotes         TEXT,
    verifiedAt                  TEXT,
    createdAt            TEXT NOT NULL DEFAULT (datetime('now')),
    updatedAt             TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Kept separate, as the notes recommend, for easier scheduling/querying
CREATE TABLE doctor_availability (
    slotId      INTEGER PRIMARY KEY AUTOINCREMENT,
    doctorId    INTEGER NOT NULL REFERENCES doctors(doctorId),
    day         TEXT NOT NULL,      -- e.g. 'Monday'
    startTime   TEXT NOT NULL,      -- '09:00'
    endTime     TEXT NOT NULL       -- '13:00'
);

CREATE TABLE appointments (
    appointmentId     INTEGER PRIMARY KEY AUTOINCREMENT,
    patientId          INTEGER NOT NULL REFERENCES patients(patientId),
    doctorId            INTEGER NOT NULL REFERENCES doctors(doctorId),
    appointmentDate      TEXT NOT NULL,
    slot                  TEXT,
    mode                  TEXT NOT NULL CHECK (mode IN ('online','offline')) DEFAULT 'online',
    status                TEXT NOT NULL CHECK (status IN ('pending','confirmed','cancelled','completed')) DEFAULT 'pending',
    paymentStatus          TEXT NOT NULL CHECK (paymentStatus IN ('paid','unpaid')) DEFAULT 'unpaid',
    meetingLink             TEXT,
    cancellationReason       TEXT,
    createdAt                TEXT NOT NULL DEFAULT (datetime('now')),
    updatedAt                 TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE medical_records (
    recordId      INTEGER PRIMARY KEY AUTOINCREMENT,
    patientId      INTEGER NOT NULL REFERENCES patients(patientId),
    doctorId        INTEGER NOT NULL REFERENCES doctors(doctorId),
    diagnosis        TEXT,
    prescription      TEXT,
    notes              TEXT,
    reportUrl           TEXT,
    followUpDate         TEXT,
    createdAt             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE chats (
    chatId            INTEGER PRIMARY KEY AUTOINCREMENT,
    participants        TEXT NOT NULL,   -- JSON array of userIds
    chatType              TEXT NOT NULL CHECK (chatType IN ('ai','doctor')) DEFAULT 'ai',
    aiEnabled             INTEGER NOT NULL DEFAULT 1,
    lastMessage             TEXT,
    lastMessageTime           TEXT
);

CREATE TABLE messages (
    messageId       INTEGER PRIMARY KEY AUTOINCREMENT,
    chatId           INTEGER NOT NULL REFERENCES chats(chatId),
    senderId          INTEGER,
    senderType         TEXT NOT NULL CHECK (senderType IN ('patient','doctor','ai')),
    message             TEXT,
    messageType           TEXT NOT NULL CHECK (messageType IN ('text','image','report','doctor_suggestion')) DEFAULT 'text',
    timestamp             TEXT NOT NULL DEFAULT (datetime('now')),
    isRead                 INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE payments (
    paymentId       INTEGER PRIMARY KEY AUTOINCREMENT,
    appointmentId     INTEGER NOT NULL REFERENCES appointments(appointmentId),
    patientId          INTEGER NOT NULL REFERENCES patients(patientId),
    doctorId            INTEGER NOT NULL REFERENCES doctors(doctorId),
    amount               REAL NOT NULL,
    paymentMethod         TEXT CHECK (paymentMethod IN ('card','upi','wallet')),
    transactionId           TEXT,
    status                   TEXT NOT NULL CHECK (status IN ('success','failed','pending','refunded')) DEFAULT 'pending',
    createdAt                 TEXT NOT NULL DEFAULT (datetime('now'))
);

-- A pharmacy account. If ownerDoctorId is set, the pharmacy identifies itself
-- as that doctor's own dispensary. Every pharmacy account needs a doctor
-- (approverDoctorId) to approve it before it can sign in.
CREATE TABLE pharmacies (
    pharmacyId        INTEGER PRIMARY KEY REFERENCES users(userId),
    pharmacyName        TEXT NOT NULL,
    licenseNumber        TEXT,
    address                TEXT,
    ownerDoctorId            INTEGER REFERENCES doctors(doctorId),
    approverDoctorId          INTEGER REFERENCES doctors(doctorId),
    approvalStatus              TEXT NOT NULL CHECK (approvalStatus IN ('pending','approved','rejected')) DEFAULT 'pending',
    approvedAt                    TEXT,
    createdAt                      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE prescriptions (
    prescriptionId    INTEGER PRIMARY KEY AUTOINCREMENT,
    recordId            INTEGER REFERENCES medical_records(recordId),
    patientId             INTEGER NOT NULL REFERENCES patients(patientId),
    doctorId               INTEGER NOT NULL REFERENCES doctors(doctorId),
    medicines                TEXT NOT NULL,     -- JSON array [{name,dosage,frequency,duration}]
    notes                      TEXT,
    suggestedPharmacyId          INTEGER REFERENCES pharmacies(pharmacyId),
    imagePath                      TEXT,
    createdAt                        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE prescription_orders (
    orderId          INTEGER PRIMARY KEY AUTOINCREMENT,
    prescriptionId     INTEGER NOT NULL REFERENCES prescriptions(prescriptionId),
    patientId            INTEGER NOT NULL REFERENCES patients(patientId),
    pharmacyId             INTEGER NOT NULL REFERENCES pharmacies(pharmacyId),
    status                   TEXT NOT NULL CHECK (status IN ('placed','processing','ready','fulfilled','cancelled')) DEFAULT 'placed',
    createdAt                  TEXT NOT NULL DEFAULT (datetime('now')),
    updatedAt                    TEXT NOT NULL DEFAULT (datetime('now'))
);
