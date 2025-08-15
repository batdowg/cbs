import csv, io, os, re, zipfile, json, smtplib, ssl
from datetime import datetime
from email.message import EmailMessage
from functools import wraps
from flask import Flask, request, send_file, send_from_directory, Response, url_for, session, redirect, abort
import psycopg2
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from werkzeug.security import generate_password_hash, check_password_hash

# ---------- config ----------
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD")
DB_HOST = os.environ.get("DB_HOST","db")
DB_USER = os.environ.get("DB_USER","cbs")
DB_NAME = os.environ.get("DB_NAME","cbs")
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT","587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
SMTP_FROM = os.environ.get("SMTP_FROM")
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME","Kepner-Tregoe Certificates")
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY","dev-insecure")

TEMPLATE_PATH = "/app/assets/certificate_template.pdf"
SITE_OUT_DIR = "/srv/issued"
MM = 2.83465
NAME_Y = 145 * MM
WORKSHOP_Y = 102 * MM
DATE_Y = 83 * MM
NAME_MAX_PT = 48
NAME_MIN_PT = 32
SIDE_MARGIN_MM = 40.0

# ---------- db ----------
def conn():
    return psycopg2.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, dbname=DB_NAME)

def ensure_defaults(cx):
    with cx.cursor() as cur:
        cur.execute("create extension if not exists pgcrypto;")
        cur.execute("select client_id from client limit 1;")
        r = cur.fetchone()
        if r: return r[0]
        cur.execute("insert into client(name, data_region, status) values (%s,'US_CA','active') returning client_id", ("Default Client",))
        return cur.fetchone()[0]

# ---------- helpers ----------
def sanitize(s): return re.sub(r"[^A-Za-z0-9_\-\.]", "_", s or "")

def autoshrink_name(width_pts, text):
    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans-Italic","DejaVuSans-Oblique.ttf"))
        font = "DejaVuSans-Italic"
    except:
        font = "Helvetica-Oblique"
    size = NAME_MAX_PT
    while size >= NAME_MIN_PT:
        if pdfmetrics.stringWidth(text, font, size) <= width_pts: return font, size
        size -= 1
    return font, NAME_MIN_PT

def stamp_certificate(name, workshop, date_line, out_path):
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError("certificate_template.pdf not found in /app/assets")
    reader = PdfReader(TEMPLATE_PATH); page = reader.pages[0]
    w = float(page.mediabox.width)
    usable_pts = ((w/MM) - (SIDE_MARGIN_MM*2)) * MM
    font, pt = autoshrink_name(usable_pts, name)
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(page.mediabox.width, page.mediabox.height))
    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", "DejaVuSans.ttf"))
        pdfmetrics.registerFont(TTFont("DejaVuSans-Italic","DejaVuSans-Oblique.ttf"))
    except:
        pass
    c.setFont(font, pt); c.drawCentredString(float(page.mediabox.width)/2, NAME_Y, name)
    c.setFont("DejaVuSans" if "DejaVuSans" in pdfmetrics.getRegisteredFontNames() else "Helvetica", 30); c.drawCentredString(float(page.mediabox.width)/2, WORKSHOP_Y, workshop)
    c.setFont("DejaVuSans" if "DejaVuSans" in pdfmetrics.getRegisteredFontNames() else "Helvetica", 18); c.drawCentredString(float(page.mediabox.width)/2, DATE_Y, date_line)
    c.save(); packet.seek(0)
    overlay = PdfReader(packet).pages[0]; page.merge_page(overlay)
    writer = PdfWriter(); writer.add_page(page)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f: writer.write(f)

def send_cert_email(to_email, learner_name, workshop, date_line, pdf_path):
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS, SMTP_FROM]): return False
    msg = EmailMessage()
    msg["To"] = to_email
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM}>"
    msg["Subject"] = f"Your KT Certificate - {workshop}"
    msg.set_content(f"Hello {learner_name},\n\nAttached is your Kepner-Tregoe certificate for {workshop} completed on {date_line}.\n\nRegards,\nKepner-Tregoe")
    with open(pdf_path, "rb") as f: data = f.read()
    msg.add_attachment(data, maintype="application", subtype="pdf", filename=os.path.basename(pdf_path))
    ctx = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.starttls(context=ctx); s.login(SMTP_USER, SMTP_PASS); s.send_message(msg)
    return True

# ---------- RBAC ----------
def login_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if not session.get("uid"): return redirect("/login")
        return f(*a, **kw)
    return wrap

def is_staff():
    roles = session.get("roles") or {}
    return any([roles.get("staff"), roles.get("admin"), roles.get("crm"), roles.get("delivery"), roles.get("contractor")])

def staff_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if not session.get("uid"): return redirect("/login")
        if not is_staff(): return abort(403)
        return f(*a, **kw)
    return wrap

def admin_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if not session.get("uid"): return redirect("/login")
        if not (session.get("roles") or {}).get("admin"): return abort(403)
        return f(*a, **kw)
    return wrap

def roles_required_any(*names):
    def deco(f):
        @wraps(f)
        def wrap(*a, **kw):
            if not session.get("uid"): return redirect("/login")
            roles = session.get("roles") or {}
            if not any(roles.get(n) for n in names): return abort(403)
            return f(*a, **kw)
        return wrap
    return deco

# ---------- auth ----------
@app.get("/login")
def login_form():
    return Response("""
    <h2>Login</h2>
    <form method="POST" action="/login">
      <label>Email <input type="email" name="email" required></label>
      <label style="margin-left:12px">Password <input type="password" name="password" required></label>
      <button type="submit">Login</button>
    </form>
    """, mimetype="text/html")

@app.post("/login")
def login_post():
    email = (request.form.get("email") or "").strip().lower()
    pw = request.form.get("password") or ""
    with conn() as cx, cx.cursor() as cur:
        cur.execute("""select user_account_id, password_hash,
                              is_kt_admin, is_kt_crm, is_kt_delivery, is_kt_contractor, is_kt_staff
                       from user_account where email=%s and status='active' limit 1""", (email,))
        row = cur.fetchone()
        if not row or not row[1] or not check_password_hash(row[1], pw):
            return Response("<p>Invalid email or password</p><p><a href=\"/login\">Back</a></p>", mimetype="text/html", status=401)
        session["uid"] = str(row[0]); session["email"] = email
        session["roles"] = dict(admin=row[2], crm=row[3], delivery=row[4], contractor=row[5], staff=row[6])
    return redirect("/")

@app.get("/logout")
def logout():
    session.clear(); return redirect("/login")

# ---------- dashboard ----------
def _get_counts():
    data = {"users":0,"users_active":0,"sessions":0,"certs":0,"last_cert_date":""}
    with conn() as cx, cx.cursor() as cur:
        cur.execute("select count(*) from user_account"); data["users"] = cur.fetchone()[0]
        cur.execute("select count(*) from user_account where status='active'"); data["users_active"] = cur.fetchone()[0]
        cur.execute("select count(*) from session"); data["sessions"] = cur.fetchone()[0]
        cur.execute("select count(*), max(issued_at) from credential where type='certificate'")
        r = cur.fetchone(); data["certs"] = r[0] or 0
        if r[1]: data["last_cert_date"] = r[1].strftime("%Y-%m-%d %H:%M")
    return data

def _role_names():
    r = session.get("roles") or {}
    out = []
    if r.get("admin"): out.append("Admin")
    if r.get("crm"): out.append("CRM")
    if r.get("delivery"): out.append("Delivery")
    if r.get("contractor"): out.append("Contractor")
    if r.get("staff"): out.append("Staff")
    return ", ".join(out) or "Learner"

@app.get("/")
@login_required
def home():
    email = session.get("email","")
    roles = _role_names()
    stats = _get_counts() if is_staff() else None

    links = []
    if is_staff():
        links.append(('<a href="/sessions">Sessions</a>', "List and create sessions"))
        links.append(('<a href="/importer">Import CSV</a>', "Upload CSV to issue certificates"))
        links.append(('<a href="/cert-form">Create Certificates</a>', "One page form for multiple learners"))
        links.append(('<a href="/issued">Issued PDFs</a>', "Browse generated PDFs"))
    if (session.get("roles") or {}).get("admin"):
        links.append(('<a href="/users">User Management</a>', "Create, edit, reset, deactivate"))
    base = request.path.rstrip('/') + '/'
    links.append((f'<a href="{base}my-certificates">My Certificates</a>', "Learner portal"))
    links.append((f'<a href="{base}logout">Logout</a>', "End session"))

    html = [
        f"<h2>Welcome</h2>",
        f"<p>Signed in as {email} ({roles})</p>",
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px'>"
    ]
    for a, desc in links:
        html.append(f"<div style='border:1px solid #ccc;border-radius:8px;padding:12px'><div style='font-size:18px;margin-bottom:6px'>{a}</div><div style='color:#555;font-size:14px'>{desc}</div></div>")
    html.append("</div>")
    if stats:
        html.append("""
        <h3 style="margin-top:16px">Summary</h3>
        <table border="1" cellpadding="6" cellspacing="0">
          <tr><th>Total users</th><td>{users}</td></tr>
          <tr><th>Active users</th><td>{users_active}</td></tr>
          <tr><th>Sessions</th><td>{sessions}</td></tr>
          <tr><th>Certificates issued</th><td>{certs}</td></tr>
          <tr><th>Last certificate</th><td>{last_cert_date}</td></tr>
        </table>
        """.format(**stats))
    return Response("\n".join(html), mimetype="text/html")

# ---------- file ACL ----------
def user_allowed_files(user_id):
    allowed = set()
    with conn() as cx, cx.cursor() as cur:
        cur.execute("""
            select s.session_id, coalesce(c.display_name_on_credential,'')
            from credential c
            join registration r on r.registration_id = c.registration_id
            join session s on s.session_uid = r.session_uid
            where r.user_account_id=%s and c.type='certificate'
        """, (user_id,))
        for sess_id, disp_name in cur.fetchall():
            sid = sanitize(sess_id); dn = sanitize(disp_name)
            allowed.add(f"issued/{sid}/{sid}_{dn}.pdf")
    return allowed

@app.get("/files/<path:subpath>")
@login_required
def files(subpath):
    if is_staff(): return send_from_directory("/srv", subpath, as_attachment=False)
    uid = session.get("uid"); p = subpath.replace("\\","/")
    if p in user_allowed_files(uid): return send_from_directory("/srv", p, as_attachment=False)
    return abort(403)

# ---------- staff tools ----------
def upsert_workshop(cur, code, name):
    if not code: return None
    cur.execute("insert into workshop_type(code,name,active) values (%s,%s,true) on conflict(code) do update set name=excluded.name returning workshop_type_id", (code, name or code))
    return cur.fetchone()[0]

def upsert_session(cur, client_id, row, workshop_type_id):
    cur.execute("select session_uid from session where session_id=%s", (row["session_id"],))
    r = cur.fetchone()
    if r: return r[0]
    cur.execute("""
      insert into session(client_id,session_id,workshop_type_id,title,start_date,end_date,timezone,delivery_type,session_language,status)
      values (%s,%s,%s,%s,%s,%s,%s,%s,%s,'scheduled')
      returning session_uid
    """, (client_id,row["session_id"],workshop_type_id,row["session_title"],row["start_date"],row["end_date"],row["timezone"],row["delivery_type"],row.get("session_language") or None))
    return cur.fetchone()[0]

def upsert_user(cur, client_id, row):
    cur.execute("select user_account_id from user_account where lower(email)=lower(%s)", (row["learner_email"],))
    r = cur.fetchone()
    if r:
        uid = r[0]
        if row.get("certificate_display_name"):
            cur.execute("update user_account set certificate_display_name=%s where user_account_id=%s and (certificate_display_name is null or certificate_display_name='')",
                        (row["certificate_display_name"], uid))
        return uid
    cur.execute("""
      insert into user_account(client_id,email,auth_type,first_name,last_name,certificate_display_name,status)
      values (NULL,%s,'native',%s,%s,%s,'active') returning user_account_id
    """, (row["learner_email"],row["learner_first_name"],row["learner_last_name"],row.get("certificate_display_name") or None))
    return cur.fetchone()[0]

def upsert_registration(cur, session_uid, user_account_id, completion_date):
    cur.execute("select registration_id from registration where session_uid=%s and user_account_id=%s", (session_uid,user_account_id))
    r = cur.fetchone()
    if r:
        rid = r[0]; cur.execute("update registration set status='completed', completion_date=%s where registration_id=%s", (completion_date,rid))
        return rid
    cur.execute("""
      insert into registration(session_uid,user_account_id,status,completion_date)
      values (%s,%s,'completed',%s) returning registration_id
    """, (session_uid,user_account_id,completion_date))
    return cur.fetchone()[0]

def issue_credential(cur, registration_id, disp_name, typ, badge_code):
    cur.execute("select credential_id from credential where registration_id=%s and type=%s and version=1", (registration_id, typ))
    r = cur.fetchone()
    if r: return r[0]
    if typ == "badge":
        cur.execute("select badge_type_id from badge_type where code=%s", (badge_code,))
        b = cur.fetchone()
        cur.execute("""insert into credential(registration_id,type,badge_type_id,issued_at,display_name_on_credential)
                       values (%s,'badge',%s,now(),%s) returning credential_id""", (registration_id,b[0],disp_name))
    else:
        cur.execute("""insert into credential(registration_id,type,issued_at,display_name_on_credential)
                       values (%s,'certificate',now(),%s) returning credential_id""", (registration_id,disp_name))
    return cur.fetchone()[0]

# ---------- Sessions: list ----------
@app.get("/sessions")
@roles_required_any("admin","crm","delivery")
def sessions_list():
    q = (request.args.get("q") or "").strip().lower()
    rows = []
    with conn() as cx, cx.cursor() as cur:
        sql = """select session_uid, session_id, coalesce(title,''), 
                        to_char(start_date,'YYYY-MM-DD'),
                        to_char(end_date,'YYYY-MM-DD'),
                        coalesce(delivery_type,''), coalesce(session_language,''), status
                 from session"""
        params = []
        if q:
            sql += " where lower(session_id) like %s or lower(title) like %s"
            like = f"%{q}%"; params += [like, like]
        sql += " order by start_date desc nulls last, session_id asc limit 200"
        cur.execute(sql, params)
        rows = cur.fetchall()
    out = ["""
      <h2>Sessions</h2>
      <form method="get" action="/sessions" style="margin-bottom:10px">
        <input type="text" name="q" value="{q}" placeholder="search session id or title" size="30">
        <button type="submit">Search</button>
        <a href="/sessions" style="margin-left:6px">Clear</a>
        <a href="/sessions/new" style="margin-left:12px">+ New session</a>
        <a href="/" style="margin-left:12px">Home</a>
      </form>
      <table border="1" cellpadding="6" cellspacing="0">
        <tr><th>Session ID</th><th>Title</th><th>Start</th><th>End</th><th>Delivery</th><th>Lang</th><th>Status</th></tr>
    """.format(q=q)]
    for uid,sid,title,sd,ed,dt,lang,st in rows:
        out.append(f"<tr><td>{sid}</td><td>{title}</td><td>{sd or ''}</td><td>{ed or ''}</td><td>{dt}</td><td>{lang}</td><td>{st}</td></tr>")
    out.append("</table><p><a href='/'>Back</a></p>")
    return Response("\n".join(out), mimetype="text/html")

# ---------- Sessions: create ----------
@app.get("/sessions/new")
@roles_required_any("admin","crm","delivery")
def sessions_new_form():
    return Response("""
      <h2>New session</h2>
      <form method="post" action="/sessions/new">
        <p><label>Session ID <input type="text" name="session_id" required></label></p>
        <p><label>Workshop name <input type="text" name="workshop_name" required></label></p>
        <p>
          <label>Start date <input type="date" name="start_date" required></label>
          <label style="margin-left:12px">End date <input type="date" name="end_date" required></label>
        </p>
        <p>
          <label>Timezone <input type="text" name="timezone" value="UTC" required></label>
          <label style="margin-left:12px">Delivery type
            <select name="delivery_type">
              <option value="face_to_face">face_to_face</option>
              <option value="virtual">virtual</option>
              <option value="hybrid">hybrid</option>
              <option value="online">online</option>
            </select>
          </label>
          <label style="margin-left:12px">Language <input type="text" name="session_language" value="en" required></label>
        </p>
        <p><button type="submit">Create</button> <a href="/sessions">Cancel</a></p>
      </form>
    """, mimetype="text/html")

@app.post("/sessions/new")
@roles_required_any("admin","crm","delivery")
def sessions_new_post():
    sid = (request.form.get("session_id") or "").strip()
    wname = (request.form.get("workshop_name") or "").strip()
    sd = (request.form.get("start_date") or "").strip()
    ed = (request.form.get("end_date") or "").strip()
    tz = (request.form.get("timezone") or "UTC").strip()
    dtype = (request.form.get("delivery_type") or "face_to_face").strip()
    lang = (request.form.get("session_language") or "en").strip()
    if not sid or not wname or not sd or not ed:
        return Response("<p>Missing required fields</p><p><a href=\"/sessions/new\">Back</a></p>", mimetype="text/html", status=400)
    try:
        sd_dt = datetime.fromisoformat(sd)
        ed_dt = datetime.fromisoformat(ed)
    except:
        return Response("<p>Dates must be YYYY-MM-DD</p><p><a href=\"/sessions/new\">Back</a></p>", mimetype="text/html", status=400)
    code = re.sub(r"[^A-Za-z0-9]+","_", wname).upper()
    with conn() as cx, cx.cursor() as cur:
        client_id = ensure_defaults(cx)
        cur.execute("select 1 from session where session_id=%s", (sid,))
        if cur.fetchone():
            return Response("<p>Session ID already exists</p><p><a href=\"/sessions/new\">Back</a></p>", mimetype="text/html", status=400)
        wsid = upsert_workshop(cur, code, wname)
        cur.execute("""
            insert into session(client_id,session_id,workshop_type_id,title,start_date,end_date,timezone,delivery_type,session_language,status)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,'scheduled')
        """, (client_id, sid, wsid, wname, sd_dt, ed_dt, tz, dtype, lang))
        cx.commit()
    return redirect("/sessions")

# ---------- importer ----------
@app.get("/importer")
@staff_required
def importer_form():
    return Response("""
    <h2>Manual Import</h2>
    <p>Upload the CSV from our template. Certificates will be stamped and saved to <a href="/issued" target="_blank">/issued</a>.</p>
    <form method="POST" action="/importer" enctype="multipart/form-data">
      <input type="file" name="file" accept=".csv" required />
      <label style="margin-left:12px"><input type="checkbox" name="send_email" value="1"> Email PDFs to learners</label>
      <button type="submit">Import</button>
    </form>
    <p><a href="/cert-form">Or use the one-page form</a> | <a href="/users">User management</a> | <a href="/logout">Logout</a></p>
    """, mimetype="text/html")

@app.post("/importer")
@staff_required
def importer():
    if "file" not in request.files: return "No file", 400
    data = request.files["file"].read().decode("utf-8", errors="ignore")
    try: delim = csv.Sniffer().sniff(data.splitlines()[0]).delimiter
    except: delim = ';'
    reader = csv.DictReader(io.StringIO(data), delimiter=delim)
    send_flag = request.form.get("send_email") == "1"
    pdf_files = []
    with conn() as cx:
        cx.autocommit = False; client_id = ensure_defaults(cx)
        for raw in reader:
            row = {k.strip(): (v.strip() if isinstance(v,str) else v) for k,v in raw.items()}
            with cx.cursor() as cur:
                wsid = upsert_workshop(cur, row.get("workshop_type_code"), row.get("session_title"))
                sd = datetime.fromisoformat(row["start_date"]); ed = datetime.fromisoformat(row["end_date"])
                session_uid = upsert_session(cur, client_id, row, wsid)
                user_id = upsert_user(cur, client_id, row)
                reg_id = upsert_registration(cur, session_uid, user_id, ed.date())
                cur.execute("select certificate_display_name from user_account where user_account_id=%s", (user_id,))
                disp_name = cur.fetchone()[0]
                ctyp = (row.get("credential_type") or "certificate").lower(); bcode = row.get("badge_code") or None
                _ = issue_credential(cur, reg_id, disp_name, ctyp, bcode)
                date_line = ed.strftime("%-d %B %Y") if hasattr(ed,"strftime") else ed.strftime("%d %B %Y")
                out_dir = os.path.join(SITE_OUT_DIR, sanitize(row["session_id"]))
                out_path = os.path.join(out_dir, f"{sanitize(row['session_id'])}_{sanitize(disp_name)}.pdf")
                stamp_certificate(disp_name, row.get("session_title") or "", date_line, out_path)
                pdf_files.append(out_path)
                if send_flag:
                    try: send_cert_email(row["learner_email"], disp_name, row.get("session_title") or "", date_line, out_path)
                    except Exception:
                        pass
        cx.commit()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in pdf_files: z.write(p, os.path.relpath(p, "/srv"))
    buf.seek(0); return send_file(buf, as_attachment=True, download_name="issued_certificates.zip", mimetype="application/zip")

# ---------- cert form ----------
@app.get("/cert-form")
@staff_required
def cert_form():
    return Response("""
    <h2>Create Certificates</h2>
    <form id="f" method="POST" action="/cert-form">
      <fieldset>
        <legend>Workshop</legend>
        <label>Workshop name <input type="text" name="workshop_name" required /></label>
        <label style="margin-left:12px">Completion date <input type="date" name="completion_date" required /></label>
        <label style="margin-left:12px">Session ID (optional) <input type="text" name="session_id" placeholder="auto if blank" /></label>
      </fieldset>
      <h3>Learners</h3>
      <table id="t" border="1" cellpadding="4" cellspacing="0">
        <thead><tr><th>Email</th><th>First</th><th>Last</th><th>Certificate name</th><th></th></tr></thead>
        <tbody></tbody>
      </table>
      <p><button type="button" id="addBtn">Add learner</button></p>
      <p><label><input type="checkbox" name="send_email" value="1"> Email PDFs to learners</label></p>
      <input type="hidden" name="learners_json" id="learners_json" />
      <p><button type="submit">Create certificates</button> <a href="/">Back</a> | <a href="/logout">Logout</a></p>
    </form>
    <script>
      function addRow(v){ v = v || {};
        const tb = document.querySelector("#t tbody");
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><input type="email" value="${v.email||''}" required></td>
          <td><input type="text"  value="${v.first||''}" required></td>
          <td><input type="text"  value="${v.last||''}" required></td>
          <td><input type="text"  value="${v.cert||''}" required></td>
          <td><button type="button" onclick="this.closest('tr').remove()">Remove</button></td>`;
        tb.appendChild(tr);
      }
      document.getElementById("addBtn").addEventListener("click", () => addRow());
      addRow(); addRow(); addRow();
      document.getElementById("f").addEventListener("submit", function(ev){
        const rows = [];
        document.querySelectorAll("#t tbody tr").forEach(tr => {
          const [email, first, last, cert] = [...tr.querySelectorAll("input")].map(i => i.value.trim());
          if (email) rows.push({email, first, last, cert});
        });
        if (rows.length === 0) { ev.preventDefault(); alert("Add at least one learner"); return; }
        document.getElementById("learners_json").value = JSON.stringify(rows);
      });
    </script>
    """, mimetype="text/html")

@app.post("/cert-form")
@staff_required
def cert_form_post():
    wname = request.form.get("workshop_name","").strip()
    cdate = request.form.get("completion_date","").strip()
    sid = request.form.get("session_id","").strip()
    send_flag = request.form.get("send_email") == "1"
    learners_json = request.form.get("learners_json","[]")
    if not wname or not cdate: return "Missing workshop name or completion date", 400
    try: ed = datetime.fromisoformat(cdate)
    except: return "completion_date must be YYYY-MM-DD", 400
    try: learners = json.loads(learners_json)
    except: return "Bad learners_json", 400
    if not sid: sid = "MANUAL-" + datetime.utcnow().strftime("%Y%m%d%H%M%S")
    wcode = re.sub(r"[^A-Za-z0-9]+","_", wname).upper()
    pdf_files = []
    with conn() as cx:
        cx.autocommit = False; client_id = ensure_defaults(cx)
        with cx.cursor() as cur:
            wsid = upsert_workshop(cur, wcode, wname)
            row = {"session_id": sid, "session_title": wname, "start_date": ed.isoformat(), "end_date": ed.isoformat(),
                   "timezone": "UTC", "delivery_type": "face_to_face", "session_language": "en"}
            session_uid = upsert_session(cur, client_id, row, wsid)
            for L in learners:
                if not L.get("email") or not L.get("cert"): continue
                rowL = {"learner_email": L["email"], "learner_first_name": L.get("first",""), "learner_last_name": L.get("last",""),
                        "certificate_display_name": L["cert"]}
                user_id = upsert_user(cur, client_id, rowL)
                reg_id = upsert_registration(cur, session_uid, user_id, ed.date())
                cur.execute("select certificate_display_name from user_account where user_account_id=%s", (user_id,))
                disp_name = cur.fetchone()[0]
                _ = issue_credential(cur, reg_id, disp_name, "certificate", None)
                date_line = ed.strftime("%-d %B %Y") if hasattr(ed,"strftime") else ed.strftime("%d %B %Y")
                out_dir = os.path.join(SITE_OUT_DIR, sanitize(sid))
                out_path = os.path.join(out_dir, f"{sanitize(sid)}_{sanitize(disp_name)}.pdf")
                stamp_certificate(disp_name, wname, date_line, out_path)
                pdf_files.append(out_path)
                if send_flag:
                    try: send_cert_email(L["email"], disp_name, wname, date_line, out_path)
                    except Exception:
                        pass
        cx.commit()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in pdf_files: z.write(p, os.path.relpath(p, "/srv"))
    buf.seek(0); return send_file(buf, as_attachment=True, download_name="issued_certificates.zip", mimetype="application/zip")

# ---------- learner ----------
@app.get("/my-certificates")
@login_required
def my_certificates():
    if is_staff(): return redirect("/issued")
    uid = session.get("uid"); links = sorted(user_allowed_files(uid))
    out = ["<h2>My Certificates</h2><ul>"] + [f'<li><a href="{url_for("files", subpath=r)}" target="_blank">{r}</a></li>' for r in links]
    base = request.path.rsplit('/', 1)[0].rstrip('/') + '/'
    out.append(f"</ul><p><a href='{base}'>Back</a> | <a href='{base}logout'>Logout</a></p>")
    return Response("\n".join(out), mimetype="text/html")

# ---------- User Management ----------
def role_cols(): return ["is_kt_admin","is_kt_crm","is_kt_delivery","is_kt_contractor","is_kt_staff"]

@app.get("/users")
@admin_required
def users_page():
    def h(s):
        s = s or ""
        return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

    q = (request.args.get("q") or "").strip().lower()
    status_f = (request.args.get("status") or "all").strip()
    role_f = {k: (request.args.get(k) == "1") for k in role_cols()}

    rows = []
    with conn() as cx, cx.cursor() as cur:
        sql = """select user_account_id,email,first_name,last_name,
                        coalesce(certificate_display_name,''), status,
                        coalesce(is_kt_admin,false),coalesce(is_kt_crm,false),
                        coalesce(is_kt_delivery,false),coalesce(is_kt_contractor,false),
                        coalesce(is_kt_staff,false)
                 from user_account"""
        cond = []; params = []
        if q:
            cond.append("(lower(email) like %s or lower(first_name) like %s or lower(last_name) like %s or lower(coalesce(certificate_display_name,'')) like %s)")
            like = f"%{q}%"; params += [like, like, like, like]
        if status_f in ("active","inactive"):
            cond.append("status=%s"); params.append(status_f)
        for col, want in role_f.items():
            if want: cond.append(f"coalesce({col},false)=true")
        if cond: sql += " where " + " and ".join(cond)
        sql += " order by is_kt_staff desc, email asc"
        cur.execute(sql, params)
        rows = cur.fetchall()

    def chk(name): return "checked" if role_f.get(name) else ""
    def sel(v): return "selected" if status_f == v else ""

    out = [f"""
      <h2>User Management</h2>
      <form method="get" action="/users" style="margin-bottom:10px">
        <input type="text" name="q" value="{h(q)}" placeholder="search email, name, cert name" size="30">
        <label style="margin-left:8px">Status
          <select name="status">
            <option value="all" {sel('all')}>all</option>
            <option value="active" {sel('active')}>active</option>
            <option value="inactive" {sel('inactive')}>inactive</option>
          </select>
        </label>
        <span style="margin-left:8px">
          <label><input type="checkbox" name="is_kt_admin" {chk('is_kt_admin')} value="1"> Admin</label>
          <label><input type="checkbox" name="is_kt_crm" {chk('is_kt_crm')} value="1"> CRM</label>
          <label><input type="checkbox" name="is_kt_delivery" {chk('is_kt_delivery')} value="1"> Delivery</label>
          <label><input type="checkbox" name="is_kt_contractor" {chk('is_kt_contractor')} value="1"> Contractor</label>
          <label><input type="checkbox" name="is_kt_staff" {chk('is_kt_staff')} value="1"> Staff</label>
        </span>
        <button type="submit" style="margin-left:8px">Apply</button>
        <a href="/users" style="margin-left:6px">Clear</a>
      </form>

      <h3>Create user</h3>
      <form method="post" action="/users/create">
        <input type="email" name="email" required placeholder="email">
        <input type="text" name="first" required placeholder="first name">
        <input type="text" name="last" required placeholder="last name">
        <label><input type="checkbox" name="is_kt_admin"> Admin</label>
        <label><input type="checkbox" name="is_kt_crm"> CRM</label>
        <label><input type="checkbox" name="is_kt_delivery"> Delivery</label>
        <label><input type="checkbox" name="is_kt_contractor"> Contractor</label>
        <select name="status"><option value="active">active</option><option value="inactive">inactive</option></select>
        <button type="submit">Create (password KTPass123)</button>
      </form>

      <h3>All users</h3>
      <table border="1" cellpadding="4" cellspacing="0">
        <tr><th>Email</th><th>Name</th><th>Cert display name</th><th>Status</th><th>Admin</th><th>CRM</th><th>Delivery</th><th>Contractor</th><th>Staff</th><th>Actions</th></tr>
    """]

    for uid,email,first,last,cert_name,status,a,c,d,co,st in rows:
        out.append(f"""
        <tr>
          <form method="post" action="/users/update/{uid}">
          <td>{h(email)}</td>
          <td>{h(first)} {h(last)}</td>
          <td><input type="text" name="certificate_display_name" value="{h(cert_name)}" size="24"></td>
          <td>
            <select name="status">
              <option value="active" {'selected' if status=='active' else ''}>active</option>
              <option value="inactive" {'selected' if status!='active' else ''}>inactive</option>
            </select>
          </td>
          <td><input type="checkbox" name="is_kt_admin" {'checked' if a else ''}></td>
          <td><input type="checkbox" name="is_kt_crm" {'checked' if c else ''}></td>
          <td><input type="checkbox" name="is_kt_delivery" {'checked' if d else ''}></td>
          <td><input type="checkbox" name="is_kt_contractor" {'checked' if co else ''}></td>
          <td><input type="checkbox" name="is_kt_staff" {'checked' if st else ''}></td>
          <td>
            <button type="submit">Save</button>
          </form>
          <form method="post" action="/users/pwreset/{uid}" style="display:inline"><button type="submit">Reset PW</button></form>
          <form method="post" action="/users/delete/{uid}" style="display:inline" onsubmit="return confirm('Delete this user?')"><button type="submit">Delete</button></form>
          </td>
        </tr>
        """)
    out.append("</table><p><a href='/'>Back</a> | <a href='/logout'>Logout</a></p>")
    return Response("\n".join(out), mimetype="text/html")

def _coerce_bool(form, name): return True if form.get(name) in ["on","true","1","yes"] else False

@app.post("/users/create")
@admin_required
def users_create():
    email = (request.form.get("email") or "").strip().lower()
    first = (request.form.get("first") or "").strip()
    last  = (request.form.get("last") or "").strip()
    status = (request.form.get("status") or "active").strip()
    flags = {k:_coerce_bool(request.form,k) for k in ["is_kt_admin","is_kt_crm","is_kt_delivery","is_kt_contractor","is_kt_staff"]}
    if any([flags["is_kt_admin"],flags["is_kt_crm"],flags["is_kt_delivery"],flags["is_kt_contractor"]]) and not flags["is_kt_staff"]:
        flags["is_kt_staff"] = True
    pw_hash = generate_password_hash("KTPass123")
    with conn() as cx, cx.cursor() as cur:
        cur.execute("select user_account_id from user_account where lower(email)=%s", (email,))
        if cur.fetchone():
            return Response("<p>Email already exists. <a href='/users'>Back</a></p>", mimetype="text/html", status=400)
        cols = ["client_id","email","auth_type","first_name","last_name","password_hash","status"]
        vals = [None,email,"native",first,last,pw_hash,status]
        for k,v in flags.items(): cols.append(k); vals.append(v)
        cur.execute(f"insert into user_account ({','.join(cols)}) values ({','.join(['%s']*len(vals))})", vals)
    return redirect("/users")

@app.post("/users/update/<user_id>")
@admin_required
def users_update(user_id):
    status = (request.form.get("status") or "active").strip()
    cert_name = (request.form.get("certificate_display_name") or "").strip()
    flags = {k:_coerce_bool(request.form,k) for k in ["is_kt_admin","is_kt_crm","is_kt_delivery","is_kt_contractor","is_kt_staff"]}
    if any([flags["is_kt_admin"],flags["is_kt_crm"],flags["is_kt_delivery"],flags["is_kt_contractor"]]) and not flags["is_kt_staff"]:
        flags["is_kt_staff"] = True
    sets = ["status=%s","certificate_display_name=%s"]; params=[status, cert_name]
    for k,v in flags.items(): sets.append(f"{k}=%s"); params.append(v)
    params.append(user_id)
    with conn() as cx, cx.cursor() as cur:
        cur.execute(f"update user_account set {', '.join(sets)} where user_account_id=%s", params)
    return redirect("/users")

@app.post("/users/pwreset/<user_id>")
@admin_required
def users_pwreset(user_id):
    pw_hash = generate_password_hash("KTPass123")
    with conn() as cx, cx.cursor() as cur:
        cur.execute("update user_account set password_hash=%s where user_account_id=%s", (pw_hash,user_id))
    return redirect("/users")

@app.post("/users/delete/<user_id>")
@admin_required
def users_delete(user_id):
    with conn() as cx, cx.cursor() as cur:
        cur.execute("select 1 from registration where user_account_id=%s limit 1",(user_id,))
        if cur.fetchone():
            cur.execute("""
                update user_account
                   set status='inactive',
                       is_kt_admin=false,
                       is_kt_crm=false,
                       is_kt_delivery=false,
                       is_kt_contractor=false,
                       is_kt_staff=false
                 where user_account_id=%s
            """,(user_id,))
        else:
            cur.execute("delete from user_account where user_account_id=%s",(user_id,))
    return redirect("/users")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
