import os
import re
import sqlite3
from datetime import date
from io import BytesIO

import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

DB_FILE = "requisitions.db"

APPLICATION_TYPES = [
    "Bonafide", "Student Certificate", "Scholarship", "NOC",
    "Academic Permission", "Examination", "Internship", "Placement",
    "Other Request",
]

DECLARATION = (
    "I certify that the information provided above is correct and that the request "
    "is being submitted for academic purposes. I understand that the request will be "
    "processed as per applicable Institute/University rules and within the stipulated "
    "processing time."
)

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
MOBILE_RE = re.compile(r"^(\+91[- ]?)?[6-9]\d{9}$")  # Indian 10-digit mobile


# ---------------------------------------------------------------- storage
def init_db():
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS requisitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                req_no TEXT, department TEXT, student_name TEXT, roll_no TEXT,
                semester TEXT, division TEXT, contact TEXT, app_type TEXT,
                purpose TEXT, docs_attached TEXT, doc_names TEXT,
                req_date TEXT, status TEXT DEFAULT 'Submitted'
            )"""
        )


def save_record(d):
    with sqlite3.connect(DB_FILE) as con:
        cur = con.execute(
            """INSERT INTO requisitions (department, student_name, roll_no,
               semester, division, contact, app_type, purpose, docs_attached,
               doc_names, req_date) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (d["department"], d["name"], d["roll"], d["semester"], d["division"],
             d["contact"], d["app_type"], d["purpose"], d["docs_attached"],
             d["doc_names"], d["date"]),
        )
        req_no = f"REQ-{date.today().year}-{cur.lastrowid:04d}"
        con.execute("UPDATE requisitions SET req_no=? WHERE id=?",
                    (req_no, cur.lastrowid))
    return req_no


def fetch_all():
    with sqlite3.connect(DB_FILE) as con:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(
            "SELECT * FROM requisitions ORDER BY id DESC")]


# ---------------------------------------------------------------- validation
def validate(d, declared):
    errors = []
    required = {
        "department": "Name of Department", "name": "Student Name",
        "roll": "Roll Number", "semester": "Semester", "division": "Division",
        "contact": "Email / Mobile Number", "purpose": "Purpose / Details",
    }
    for key, label in required.items():
        if not d[key].strip():
            errors.append(f"{label} is required.")
    c = d["contact"].strip()
    if c:
        if "@" in c:
            if not EMAIL_RE.match(c):
                errors.append("Email address is not valid.")
        else:
            digits = re.sub(r"[\s-]", "", c)
            if not MOBILE_RE.match(digits):
                errors.append("Mobile number must be a valid 10-digit number.")
    if d["docs_attached"] == "Yes" and not d["doc_names"].strip():
        errors.append("Enter the name(s) of the supporting document(s).")
    if not declared:
        errors.append("You must accept the student declaration.")
    return errors


# ---------------------------------------------------------------- PDF
LOGO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
LEFT, RIGHT = 45, 550  # page margins in points


def build_pdf(d, req_no):
    """Draw the form on an A4 page following the institute's requisition form."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    H = A4[1]
    Y = lambda top: H - top  # convert "distance from top" to PDF y

    def text(x, top, t, font="Helvetica", size=10, align="left"):
        c.setFont(font, size)
        {"left": c.drawString, "right": c.drawRightString,
         "center": c.drawCentredString}[align](x, Y(top), t)

    def line(x1, x2, top, w=0.6):
        c.setLineWidth(w)
        c.line(x1, Y(top), x2, Y(top))

    def field(label, x, top, x_end, value="", bold=False, size=10):
        """Label, then a ruled line (x_end) with the value written on it."""
        f = "Helvetica-Bold" if bold else "Helvetica"
        text(x, top, label, f, size)
        x0 = x + stringWidth(label, f, size) + 4
        line(x0, x_end, top + 2)
        if value:  # shrink long values so they stay on the ruled line
            vs = size
            while stringWidth(value, "Helvetica", vs) > x_end - x0 - 6 and vs > 6:
                vs -= 0.5
            text(x0 + 3, top, value, "Helvetica", vs)

    def box(x, top, checked):
        c.setLineWidth(0.8)
        c.rect(x, Y(top) - 1, 8, 8)
        if checked:
            c.setLineWidth(1.4)
            c.line(x + 1.5, Y(top) + 0.5, x + 6.5, Y(top) + 5.5)
            c.line(x + 1.5, Y(top) + 5.5, x + 6.5, Y(top) + 0.5)

    def options(items, selected, x, top, x_max, gap=12, lh=17):
        """Flow check-box options across lines; returns the last line's top."""
        for it in items:
            w = 12 + stringWidth(it, "Helvetica", 10)
            if x + w > x_max:
                x, top = LEFT, top + lh
            box(x, top, it == selected)
            text(x + 12, top, it)
            x += w + gap
        return top

    def para(t, top, size=9.5, lh=12.5, font="Helvetica"):
        for ln in simpleSplit(t, font, size, RIGHT - LEFT):
            text(LEFT, top, ln, font, size)
            top += lh
        return top

    # ---- header box: logo | title
    c.setLineWidth(0.9)
    c.rect(LEFT, Y(95), RIGHT - LEFT, 55)
    c.line(LEFT + 160, Y(40), LEFT + 160, Y(95))
    if os.path.exists(LOGO_FILE):
        c.drawImage(LOGO_FILE, LEFT + 30, Y(78), width=100, height=100 * 73 / 199,
                    mask="auto")
    text(LEFT + 80, 89, "(Autonomous College Affiliated to University of Mumbai)",
         size=5.5, align="center")
    cx = LEFT + 160 + (RIGHT - LEFT - 160) / 2
    text(cx, 64, "STUDENT ACADEMIC REQUISITION", "Helvetica-Bold", 15, "center")
    text(cx, 82, "FORM", "Helvetica-Bold", 15, "center")

    # ---- department / outward no. / date
    field("Name of the Department.:", LEFT, 125, 330, d["department"], bold=True)
    field("Department Outward No.:", 340, 125, RIGHT, "", bold=True)   # office use
    field("Date:", LEFT, 148, 200, d["date"], bold=True)
    text(RIGHT, 148, f"Requisition No.: {req_no}", size=8.5, align="right")
    line(LEFT, RIGHT, 158, 1)

    # ---- processing time note
    c.setFont("Helvetica-Bold", 9.5)
    text(LEFT, 174, "Processing Time:", "Helvetica-Bold", 9.5)
    note = ("The request will normally be processed within 4 working days after "
            "receiving the completed form and all required supporting documents. "
            "Students are advised to apply in advance, as incomplete applications "
            "may require additional processing time.")
    lead = stringWidth("Processing Time: ", "Helvetica-Bold", 9.5)
    words, top, x, first = note.split(), 174, LEFT + lead, True
    for w in words:
        ww = stringWidth(w + " ", "Helvetica", 9.5)
        if x + ww > RIGHT:
            x, top = LEFT, top + 12.5
        text(x, top, w, size=9.5)
        x += ww
    line(LEFT, RIGHT, top + 8, 0.8)

    # ---- 1. student details
    top += 30
    text(LEFT, top, "1. STUDENT DETAILS", "Helvetica-Bold", 10.5)
    top += 22
    field("Name of Student:", LEFT, top, 430, d["name"])
    top += 26
    field("Roll No.:", LEFT, top, 210, d["roll"])
    field("Semester:", 230, top, 310, d["semester"])
    field("Division:", 330, top, 410, d["division"])
    top += 26
    field("Email / Mobile:", LEFT, top, 450, d["contact"])
    top += 26
    prefix = "Application for \u2013"
    text(LEFT, top, prefix)
    top = options(APPLICATION_TYPES, d["app_type"], LEFT + stringWidth(prefix, "Helvetica", 10) + 8,
                  top, RIGHT)

    # ---- 2. purpose
    top += 30
    text(LEFT, top, "2. PURPOSE / BRIEF DETAILS OF REQUEST", "Helvetica-Bold", 10.5)
    lines = []
    for chunk in d["purpose"].splitlines() or [""]:
        lines += simpleSplit(chunk, "Helvetica", 10, RIGHT - LEFT - 6) or [""]
    for i in range(max(3, len(lines))):
        top += 20
        line(LEFT, RIGHT, top + 2)
        if i < len(lines):
            text(LEFT + 3, top, lines[i])

    # ---- 3. supporting documents
    top += 30
    text(LEFT, top, "3. SUPPORTING DOCUMENTS", "Helvetica-Bold", 10.5)
    top += 22
    yes = d["docs_attached"] == "Yes"
    text(LEFT, top, "Documents attached:")
    box(160, top, yes);      text(172, top, "Yes")
    box(215, top, not yes);  text(227, top, "No")
    top += 24
    field("Document name(s), if applicable:", LEFT, top, RIGHT,
          d["doc_names"] if yes else "")

    # ---- 4. declaration
    top += 28
    text(LEFT, top, "4. STUDENT DECLARATION", "Helvetica-Bold", 10.5)
    top = para(DECLARATION, top + 18, 10, 13) 
    top += 14
    field("Student Signature:", LEFT, top, 270)
    field("Date:", 300, top, 420, d["date"])
    text(LEFT, top + 16, f'Declaration accepted online by {d["name"]}.',
         "Helvetica-Oblique", 8)

    # ---- 5. HoD (left blank)
    top += 44
    field("5. HoD Signature:", LEFT, top, 260, bold=True)
    field("Remarks:", 290, top, RIGHT, bold=True)
    top += 24
    top = para("Forwarded to (VICE PRINCIPAL/ CHIEF ACADEMIC OFFICER/ ACCOUNTS/ SPORTS/ "
               "PLACEMENT CELL/ SCHOLARSHIP CELL/ EXAM CELL) (if required)", top, 10, 14)
    top += 22
    field("Signature:", LEFT, top, 260, bold=True)
    field("Remarks:", 290, top, RIGHT, bold=True)

    # ---- 6. Principal office (left blank)
    top += 30
    text(LEFT, top, "6. PRINCIPAL OFFICE USE ONLY", "Helvetica-Bold", 10.5)
    top += 24
    text(LEFT, top, "Decision by Principal.:")
    options(["Approved", "Not Approved", "Clarification Required"], None,
            LEFT + 130, top, RIGHT, gap=16)
    top += 24
    field("Remarks (if any):", LEFT, top, RIGHT)
    top += 24
    field("Principal Signature:", LEFT, top, 300)

    c.showPage()
    c.save()
    return buf.getvalue()


def safe(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s.strip()).strip("_")


# ---------------------------------------------------------------- UI
st.set_page_config(page_title="Student Academic Requisition", page_icon="📄")
init_db()
st.title("📄 Student Academic Requisition Form")
tab_form, tab_admin = st.tabs(["Requisition Form", "Admin Dashboard"])

with tab_form:
    with st.form("req_form"):
        department = st.text_input("Name of Department")
        c1, c2 = st.columns(2)
        name = c1.text_input("Student Name")
        roll = c2.text_input("Roll Number")
        c3, c4 = st.columns(2)
        semester = c3.selectbox("Semester", [str(i) for i in range(1, 9)])
        division = c4.text_input("Division")
        contact = st.text_input("Email / Mobile Number")
        app_type = st.radio("Application Type", APPLICATION_TYPES, horizontal=True)
        purpose = st.text_area("Purpose / Brief Details of Request", max_chars=450)
        docs_attached = st.radio("Supporting documents attached?", ["No", "Yes"],
                                 horizontal=True)
        doc_names = st.text_input("Name of supporting document(s)")
        req_date = st.date_input("Date", value=date.today())
        st.markdown("**Student Declaration**")
        st.info(DECLARATION)
        declared = st.checkbox("I confirm the above declaration")
        submitted = st.form_submit_button("Generate PDF")

    if submitted:
        data = dict(department=department, name=name, roll=roll,
                    semester=semester, division=division, contact=contact,
                    app_type=app_type, purpose=purpose,
                    docs_attached=docs_attached, doc_names=doc_names,
                    date=req_date.strftime("%d-%m-%Y"))
        errs = validate(data, declared)
        if errs:
            st.session_state.pop("pdf", None)
            for e in errs:
                st.error(e)
        else:
            req_no = save_record(data)
            st.session_state["pdf"] = build_pdf(data, req_no)
            st.session_state["fname"] = f"Requisition_{safe(roll)}_{safe(name)}.pdf"
            st.session_state["req_no"] = req_no

    if "pdf" in st.session_state:
        st.success(f"Requisition {st.session_state['req_no']} saved. PDF is ready.")
        st.download_button("Download PDF", st.session_state["pdf"],
                           file_name=st.session_state["fname"],
                           mime="application/pdf")

with tab_admin:
    rows = fetch_all()
    q = st.text_input("Search (name, roll no, requisition no, type)")
    if q:
        rows = [r for r in rows if q.lower() in " ".join(map(str, r.values())).lower()]
    st.dataframe(rows, use_container_width=True)
