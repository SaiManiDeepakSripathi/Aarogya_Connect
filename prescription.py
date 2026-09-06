"""Renders a simple, clean prescription image (PNG) for a doctor's Rx."""

import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
OUT_DIR = os.path.join(os.path.dirname(__file__), "static", "prescriptions")

INK = (16, 36, 31)
INK_SOFT = (76, 98, 89)
ACCENT = (31, 122, 92)
ACCENT_SOFT = (215, 238, 227)
BORDER = (220, 230, 225)
PAPER = (255, 255, 255)

W, H_MIN = 900, 500
MARGIN = 56


def _font(name, size):
    path = os.path.join(FONT_DIR, name)
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def generate_prescription_image(prescription_id, doctor, patient, medicines, notes="", pharmacy=None):
    """
    doctor: dict with name, specialization, hospitalName
    patient: dict with name, gender, dateOfBirth (or age)
    medicines: list of dicts {name, dosage, frequency, duration}
    pharmacy: optional dict with pharmacyName, address
    Returns the web-relative path to the saved PNG.
    """
    os.makedirs(OUT_DIR, exist_ok=True)

    row_h = 34
    body_top = 300
    rows_height = max(len(medicines), 1) * row_h + 40
    footer_h = 150 if pharmacy else 110
    height = body_top + rows_height + footer_h

    img = Image.new("RGB", (W, height), PAPER)
    draw = ImageDraw.Draw(img)

    f_display = _font("DejaVuSerif-Bold.ttf", 30)
    f_sub = _font("DejaVuSans.ttf", 15)
    f_label = _font("DejaVuSans-Bold.ttf", 12)
    f_body = _font("DejaVuSans.ttf", 15)
    f_body_bold = _font("DejaVuSans-Bold.ttf", 15)
    f_rx = _font("DejaVuSerif-Bold.ttf", 34)
    f_small = _font("DejaVuSans.ttf", 12)
    f_mono = _font("DejaVuSansMono.ttf", 12)

    # header band
    draw.rectangle([0, 0, W, 118], fill=ACCENT)
    draw.text((MARGIN, 28), doctor.get("name", "Doctor"), font=f_display, fill=PAPER)
    draw.text((MARGIN, 68), f"{doctor.get('specialization','General Physician')}  ·  {doctor.get('hospitalName') or 'Independent Practice'}",
               font=f_sub, fill=(233, 251, 244))

    # divider vital-line motif
    pts = [(MARGIN, 118), (MARGIN + 40, 118), (MARGIN + 50, 118), (MARGIN + 58, 104),
           (MARGIN + 68, 132), (MARGIN + 78, 118), (MARGIN + 86, 118), (MARGIN + 94, 108),
           (MARGIN + 102, 128), (MARGIN + 110, 118), (W - MARGIN, 118)]

    y = 150
    draw.text((MARGIN, y), "PATIENT", font=f_label, fill=INK_SOFT)
    draw.text((MARGIN, y + 16), patient.get("name", "—"), font=f_body_bold, fill=INK)
    meta_bits = []
    if patient.get("gender"):
        meta_bits.append(patient["gender"])
    if patient.get("dateOfBirth"):
        meta_bits.append(f"DOB {patient['dateOfBirth']}")
    if meta_bits:
        draw.text((MARGIN, y + 38), "  ·  ".join(meta_bits), font=f_small, fill=INK_SOFT)

    right_x = W - MARGIN - 220
    draw.text((right_x, y), "DATE", font=f_label, fill=INK_SOFT)
    draw.text((right_x, y + 16), datetime.now().strftime("%d %b %Y"), font=f_body_bold, fill=INK)
    draw.text((right_x, y + 38), f"Rx #{prescription_id:05d}", font=f_mono, fill=INK_SOFT)

    draw.line([(MARGIN, y + 66), (W - MARGIN, y + 66)], fill=BORDER, width=1)

    # Rx symbol + medicines table
    ry = y + 90
    draw.text((MARGIN, ry - 4), "Rx", font=f_rx, fill=ACCENT)

    table_x = MARGIN + 60
    table_y = ry
    table_w = W - MARGIN - table_x
    draw.rectangle([table_x, table_y, table_x + table_w, table_y + 30], fill=ACCENT_SOFT)
    cols = [("MEDICINE", 0.40), ("DOSAGE", 0.20), ("FREQUENCY", 0.22), ("DURATION", 0.18)]
    cx = table_x
    for label, frac in cols:
        draw.text((cx + 10, table_y + 8), label, font=f_label, fill=ACCENT)
        cx += int(table_w * frac)

    ty = table_y + 30
    meds = medicines or [{"name": "—", "dosage": "", "frequency": "", "duration": ""}]
    for i, med in enumerate(meds):
        if i % 2 == 1:
            draw.rectangle([table_x, ty, table_x + table_w, ty + row_h], fill=(250, 252, 251))
        cx = table_x
        values = [med.get("name", ""), med.get("dosage", ""), med.get("frequency", ""), med.get("duration", "")]
        for (label, frac), val in zip(cols, values):
            draw.text((cx + 10, ty + 9), val, font=f_body, fill=INK)
            cx += int(table_w * frac)
        ty += row_h
    draw.line([(table_x, ty), (table_x + table_w, ty)], fill=BORDER, width=1)

    ny = ty + 20
    if notes:
        draw.text((MARGIN, ny), "NOTES", font=f_label, fill=INK_SOFT)
        draw.text((MARGIN, ny + 16), notes[:120], font=f_body, fill=INK)
        ny += 44

    # pharmacy suggestion strip
    if pharmacy:
        draw.rectangle([MARGIN, ny, W - MARGIN, ny + 56], outline=BORDER, width=1)
        draw.text((MARGIN + 14, ny + 10), "SUGGESTED PHARMACY", font=f_label, fill=ACCENT)
        draw.text((MARGIN + 14, ny + 28), f"{pharmacy.get('pharmacyName','')}  ·  {pharmacy.get('address') or 'Address on file'}",
                   font=f_small, fill=INK_SOFT)
        ny += 72

    # footer / signature
    fy = height - 70
    draw.line([(W - MARGIN - 200, fy), (W - MARGIN, fy)], fill=INK_SOFT, width=1)
    draw.text((W - MARGIN - 200, fy + 6), doctor.get("name", ""), font=f_body_bold, fill=INK)
    draw.text((W - MARGIN - 200, fy + 24), "Signature", font=f_small, fill=INK_SOFT)
    draw.text((MARGIN, fy + 6), "Generated by Aarogya Connect", font=f_small, fill=INK_SOFT)

    fname = f"rx_{prescription_id}.png"
    fpath = os.path.join(OUT_DIR, fname)
    img.save(fpath, "PNG")
    return f"/static/prescriptions/{fname}"
