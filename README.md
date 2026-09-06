# Aarogya Connect

A lightweight patient–doctor–pharmacy healthcare platform: HTML/CSS/JS frontend, Flask backend, SQLite database, and a rule-based AI triage chatbot that suggests available doctors.

## Run it

```bash
cd healthconnect
python3 -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000**. The database (`healthconnect.db`) is created and seeded automatically on first run. To reset it, delete `healthconnect.db` and restart.

### Testing on your phone

The app runs with `host="0.0.0.0"`, so it's reachable from other devices on the same WiFi — not just the computer running it. To open it on your phone:

1. Find your computer's local IP address (`ipconfig` on Windows, `ifconfig` or `ip addr` on Mac/Linux — look for something like `192.168.x.x`).
2. Make sure your phone is on the **same WiFi network**.
3. On your phone's browser, go to `http://<that-ip>:5000` (e.g. `http://192.168.1.42:5000`).

If it still doesn't load, your computer's firewall may be blocking incoming connections on port 5000 — allow it, or temporarily disable the firewall to test.

## Demo logins

| Role     | Email                              | Password    | Notes |
|----------|-------------------------------------|-------------|-------|
| Patient  | rahul.verma@example.com            | password123 | |
| Doctor   | ananya.rao@healthconnect.io        | password123 | Cardiologist, online, owns Sunrise Pharmacy |
| Doctor   | meera.iyer@healthconnect.io        | password123 | Starts **offline** — good for testing the availability badge |
| Doctor   | vikram.shah@healthconnect.io / arjun.nair@healthconnect.io | password123 | |
| Pharmacy | sunrise.pharmacy@healthconnect.io  | password123 | Pre-approved, owned by Dr. Ananya Rao |
| Pharmacy | citycare.pharmacy@healthconnect.io | password123 | Seeded **pending** — log in as Dr. Ananya Rao to approve it first |

## What's included

**Core platform**
- Auth — signup as patient, doctor, or pharmacy; login/logout; hashed passwords; sessions.
- Dashboard shell — left rail nav, dark/light theme toggle (`localStorage`), responsive to mobile.
- Patients, doctors, appointments, payments (simulated), medical records, profile photo upload.

**Doctor availability + direct chat**
- Doctors toggle an **Available / Offline** status from the sidebar; patients see a live status dot on every doctor card and in their Messages list.
- Patients can message any doctor directly (separate from the AI assistant) from a dedicated **Messages** panel — a real two-way thread stored in `chats`/`messages`, polled every few seconds.

**AI triage chatbot with doctor suggestions**
- Walks a patient through a fixed sequence of triage questions.
- Matches symptom keywords (chest pain, rash, joint pain, etc.) to a specialization and — the first time a match or the end of the flow is reached — surfaces a card of currently **available** doctors in that specialty, each with one-tap **Message** or **Book** actions.

**Pharmacy + prescriptions**
- Doctors write a prescription (patient + a repeatable medicine list: name/dosage/frequency/duration) and optionally suggest a pharmacy — either their **own** registered pharmacy or any other approved one.
- A branded **prescription image** (PNG) is generated server-side with the doctor's name, specialization, hospital name, patient details, the medicine table, and — if chosen — the suggested pharmacy, styled to match the app.
- Patients view their prescriptions and place an order with the suggested pharmacy or any other approved pharmacy; pharmacies see incoming orders and move them through `placed → processing → ready → fulfilled`.
- **Pharmacy signup requires doctor approval.** A pharmacy account picks a doctor to request approval from at signup and cannot log in until that doctor approves it from their **Pharmacy requests** panel.

**Certificate upload + automatic verification**
- Doctors upload a photo/scan of their medical certificate from their **Profile** panel.
- The server runs real OCR (Tesseract via `pytesseract`) on the image, then scores the extracted text against expected markers: a recognized medical degree (MBBS, MD, BDS, ...), council/registration language, and the doctor's own name appearing on the document.
- Result is one of **Verified** (name + credential markers matched), **Pending** (some markers found, routed for manual review), or **Rejected** (no readable/relevant text — e.g. a blank or unrelated image).
- Verified doctors show a **✓ Verified** badge on their profile and on their doctor card in the patient-facing directory.
- Honesty note: this is OCR + keyword/name matching, not a lookup against any real medical council database — there's no such API wired in. Treat "Verified" as "passed automated screening," not a legal credential check. Requires the `tesseract-ocr` binary installed on the host (`apt-get install tesseract-ocr` on Debian/Ubuntu) — if it's missing, uploads are safely routed to "Pending" instead of crashing.

## Project structure

```
healthconnect/
├── app.py                 # Flask routes + REST API
├── database.py             # SQLite connection + seed data
├── schema.sql               # Table definitions
├── prescription.py           # PIL-based prescription image generator
├── requirements.txt
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── signup.html            # patient / doctor / pharmacy role picker
│   └── dashboard.html
└── static/
    ├── css/style.css
    ├── js/main.js              # dashboard logic (fetches the REST API)
    ├── js/chatbot.js            # AI assistant widget + doctor-suggestion cards
    ├── uploads/                  # profile photos
    └── prescriptions/             # generated prescription PNGs
```

## Notes on simplifications

- The AI chatbot is **rule-based** (fixed question flow + keyword → specialization map), not wired to a real LLM, since no API key is configured. Swapping in an OpenAI/Anthropic call is a small, isolated change inside `app.py`'s `send_message` route.
- Doctor↔patient messaging uses simple polling (every 5s) rather than websockets — fine for a demo, but a production version would want a push channel.
- `allergies` / `chronicDiseases` are kept as text columns (the notes flagged this as optional — split into their own tables if you need to query by a specific allergy).
- A pharmacy's "own pharmacy" relationship is a single `ownerDoctorId` on the `pharmacies` table; a doctor can have multiple pharmacies registered to them if needed.
