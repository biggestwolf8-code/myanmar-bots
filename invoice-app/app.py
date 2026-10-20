"""Invoice Maker — Simple invoices, estimates & receipts.

An original invoice-maker web app: create invoices, estimates and receipts,
track clients, items and expenses, and download professional PDFs.

Env vars:
  ADMIN_PASSWORD  Password for the /admin panel (required)
  DATA_DIR        Storage dir (default "."; use "/data" with a Railway
                  volume so JSON + uploads survive redeploys)
  PORT            Listen port (default: 5000)

Deploy (Railway): new service from the repo, root directory `invoice-app`,
plus a volume mounted at `/data`, DATA_DIR=/data, ADMIN_PASSWORD set.
"""
import base64
import datetime
import io
import json
import os
import re
import secrets
import time
from urllib.parse import quote

from flask import (Flask, Response, abort, jsonify, redirect, request,
                   send_file, session, render_template)
from werkzeug.security import check_password_hash, generate_password_hash

DATA_DIR = os.environ.get("DATA_DIR", ".")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
PORT = int(os.environ.get("PORT", "5000"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "fonts")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
VERSION = "1.0"

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
app.permanent_session_lifetime = datetime.timedelta(days=90)

CURRENCIES = {"MMK": "K", "THB": "\u0e3f", "USD": "$"}
TYPE_TITLES = {"invoice": "Invoice", "estimate": "Estimate",
               "receipt": "Receipt"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------- storage

def _load_json(name, default):
    try:
        with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def _save_json(name, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = os.path.join(DATA_DIR, name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, os.path.join(DATA_DIR, name))


def get_secret_key():
    path = os.path.join(DATA_DIR, "secret.key")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        key = secrets.token_hex(32)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(key)
        return key


app.secret_key = get_secret_key()

# email(lowercased) -> {"pw": hash, "created": ts, "disabled": bool}
users = _load_json("invusers.json", {})
# code -> {"label": "", "used_by": email|None, "used_at": ts|None,
#          "created": ts}
codes = _load_json("invcodes.json", {})
# sid -> {"user": email, "created": ts}
sessions = _load_json("invsessions.json", {})
# email -> {"business": {...}, "clients": [], "items": [],
#           "documents": [], "expenses": [],
#           "counters": {"invoice": 0, "estimate": 0, "receipt": 0}}
invdata = _load_json("invdata.json", {})


def save_all():
    _save_json("invusers.json", users)
    _save_json("invcodes.json", codes)
    _save_json("invsessions.json", sessions)
    _save_json("invdata.json", invdata)


def default_business():
    return {"name": "", "address": "", "email": "", "phone": "",
            "website": "", "tax_id": "", "payment_details": "",
            "currency": "MMK", "logo_path": "", "signature_path": "",
            "accent_color": "#2563eb",
            "inv_prefix": "INV", "est_prefix": "EST", "rec_prefix": "REC",
            "default_tax": 0, "default_notes": "", "default_terms": "",
            "date_format": "DD Mon YYYY",
            "default_email_message": (
                "Hello {client},\n\n"
                "Please find your {type} {number} for {total} here: {link}\n\n"
                "Thank you,\n{business}")}


def user_data(email):
    d = invdata.get(email)
    if not d:
        d = {"business": default_business(), "clients": [], "items": [],
             "documents": [], "expenses": [],
             "counters": {"invoice": 0, "estimate": 0, "receipt": 0}}
        invdata[email] = d
    b = d.setdefault("business", default_business())
    for k, v in default_business().items():
        b.setdefault(k, v)
    # one-time migration: the old numeric default becomes the English
    # month-name format; an explicit later choice in Region sticks
    if b.get("date_format") == "DD-MM-YYYY" and not b.get("_date_fmt_en"):
        b["date_format"] = "DD Mon YYYY"
        b["_date_fmt_en"] = True
    d.setdefault("clients", [])
    d.setdefault("items", [])
    d.setdefault("documents", [])
    d.setdefault("expenses", [])
    d.setdefault("recurring", [])
    d.setdefault("counters", {"invoice": 0, "estimate": 0, "receipt": 0})
    return d


# ------------------------------------------------------------------ auth

_login_hits = {}


def _rate_limited(ip):
    h = _login_hits.get(ip)
    return bool(h and h["until"] > time.time())


def _rate_hit(ip):
    h = _login_hits.setdefault(ip, {"n": 0, "until": 0})
    h["n"] += 1
    if h["n"] >= 15:
        h["until"] = time.time() + 600
        h["n"] = 0


def _rate_clear(ip):
    _login_hits.pop(ip, None)


def valid_email(email):
    return bool(email) and len(email) <= 120 and EMAIL_RE.match(email)


def current_user():
    sid = session.get("sid")
    if sid and sid in sessions:
        email = sessions[sid].get("user")
        u = users.get(email)
        if u and not u.get("disabled"):
            return email
    return None


def require_user():
    email = current_user()
    if not email:
        if request.method == "GET":
            nxt = request.full_path or "/"
            if not nxt.startswith("/"):
                nxt = "/"
            abort(redirect("/login?next=" + quote(nxt, safe="")))
        abort(401)
    return email


def new_session(email):
    sid = secrets.token_hex(16)
    sessions[sid] = {"user": email,
                     "created": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    save_all()
    session["sid"] = sid
    session.permanent = True


CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def make_code():
    while True:
        c = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        if c not in codes:
            return c


def redeem_code_for(email, code):
    """Mark an invite code as used by this account. Returns (ok, message)."""
    code = (code or "").strip().upper()
    e = codes.get(code)
    if not e:
        return False, "That invite code doesn't exist."
    if e.get("used_by") and e["used_by"] != email:
        return False, "This invite code has already been used."
    e["used_by"] = email
    e["used_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return True, ""


@app.route("/i/<code>")
def invite(code):
    code = (code or "").strip().upper()
    entry = codes.get(code)
    if not entry:
        return render_template("auth.html", mode="register",
                               error="That invite code doesn't exist."), 404
    email = current_user()
    if email:
        ok, msg = redeem_code_for(email, code)
        save_all()
        if not ok:
            return render_template("auth.html", mode="register",
                                   error=msg), 403
        return redirect("/")
    used_by = entry.get("used_by")
    if used_by:
        owner = users.get(used_by) or {}
        if owner.get("kind") == "invite":
            # The link itself is the credential for instant accounts:
            # opening it signs straight back into the same account.
            new_session(used_by)
            return redirect("/")
        # Code belongs to an email account — that user signs in normally.
        session["pending_code"] = code
        return redirect("/login")
    # Fresh code: create an instant account — no signup form, no password.
    # The invite link is the only credential; the session lasts 90 days.
    acct = "invite-" + code
    users[acct] = {"pw": generate_password_hash(secrets.token_hex(16)),
                   "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   "disabled": False, "kind": "invite"}
    user_data(acct)  # initialize per-user store
    redeem_code_for(acct, code)
    save_all()
    new_session(acct)
    return redirect("/settings?first=1")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect("/")
    if request.method == "POST":
        ip = request.remote_addr or "?"
        if _rate_limited(ip):
            return render_template("auth.html", mode="login",
                                   error="Too many attempts — try again in a few minutes."), 429
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        u = users.get(email)
        if not u or u.get("disabled") or not check_password_hash(u["pw"], pw):
            _rate_hit(ip)
            return render_template("auth.html", mode="login",
                                   error="Wrong email or password."), 401
        _rate_clear(ip)
        new_session(email)
        pc = session.pop("pending_code", None)
        if pc:
            redeem_code_for(email, pc)  # best effort
            save_all()
        nxt = (request.form.get("next") or "").strip()
        if not nxt.startswith("/") or nxt.startswith("//"):
            nxt = "/"
        return redirect(nxt)
    nxt = (request.args.get("next") or "").strip()
    if not nxt.startswith("/"):
        nxt = ""
    return render_template("auth.html", mode="login", next=nxt)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect("/")
    prefill = (session.get("pending_code") or "").upper()
    if request.method == "POST":
        ip = request.remote_addr or "?"
        if _rate_limited(ip):
            return render_template("auth.html", mode="register",
                                   error="Too many attempts — try again in a few minutes."), 429
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        code = ((request.form.get("code") or "").strip().upper()
                or prefill)
        if not valid_email(email):
            return render_template("auth.html", mode="register", code=code,
                                   error="Please enter a valid email address."), 400
        if len(pw) < 6:
            return render_template("auth.html", mode="register", code=code,
                                   error="Password needs at least 6 characters."), 400
        if email in users:
            _rate_hit(ip)
            return render_template("auth.html", mode="register", code=code,
                                   error="This email already has an account — sign in instead."), 400
        if not code or code not in codes:
            return render_template("auth.html", mode="register", code=code,
                                   error="A valid invite code is required to register."), 400
        if codes[code].get("used_by") and codes[code]["used_by"] != email:
            return render_template("auth.html", mode="register", code=code,
                                   error="This invite code has already been used."), 400
        users[email] = {"pw": generate_password_hash(pw),
                        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "disabled": False}
        user_data(email)  # initialize per-user store
        redeem_code_for(email, code)
        save_all()
        _rate_clear(ip)
        session.pop("pending_code", None)
        new_session(email)
        return redirect("/settings?first=1")
    return render_template("auth.html", mode="register", code=prefill)


@app.route("/logout")
def logout():
    sid = session.pop("sid", None)
    if sid and sid in sessions:
        sessions.pop(sid, None)
        save_all()
    return redirect("/login")


# ------------------------------------------------------- document helpers

def today_str():
    return datetime.date.today().isoformat()


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def fmt_money(amount, currency):
    sym = CURRENCIES.get(currency, currency + " ")
    try:
        v = float(amount or 0)
    except (TypeError, ValueError):
        v = 0.0
    return "%s%s" % (sym, f"{v:,.2f}")


def parse_num(v, default=0.0):
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except (TypeError, ValueError):
        return default


def doc_totals(doc):
    subtotal = 0.0
    line_tax = 0.0
    for ln in doc.get("lines", []):
        lt = parse_num(ln.get("qty")) * parse_num(ln.get("rate"))
        subtotal += lt
        line_tax += lt * parse_num(ln.get("tax_pct")) / 100.0
    if doc.get("discount_type") == "percent":
        discount = subtotal * parse_num(doc.get("discount_value")) / 100.0
    else:
        discount = parse_num(doc.get("discount_value"))
    after_disc = subtotal - discount
    if doc.get("tax_type") == "percent":
        tax = after_disc * parse_num(doc.get("tax_value")) / 100.0
    else:
        tax = parse_num(doc.get("tax_value"))
    shipping = parse_num(doc.get("shipping"))
    total = after_disc + tax + line_tax + shipping
    return {"subtotal": subtotal, "discount": discount,
            "after_discount": after_disc, "tax": tax,
            "line_tax": line_tax, "shipping": shipping, "total": total}


def eff_status(doc):
    """Effective status: overdue is auto-computed for invoices."""
    st = doc.get("status", "draft")
    if doc.get("type") == "invoice" and st not in ("paid", "cancelled"):
        due = doc.get("due_date") or ""
        if due and due < today_str():
            return "overdue"
    return st


STATUS_LABELS = {"draft": "Unpaid", "sent": "Unpaid", "paid": "Paid",
                 "overdue": "Unpaid", "cancelled": "Cancelled",
                 "accepted": "Accepted", "declined": "Declined",
                 "expired": "Expired"}


def find_doc(d, doc_id):
    for doc in d["documents"]:
        if doc["id"] == doc_id:
            return doc
    return None


def find_doc_by_token(d, token):
    for doc in d["documents"]:
        if doc.get("share_token") == token:
            return doc
    return None


def find_client(d, client_id):
    for c in d["clients"]:
        if c["id"] == client_id:
            return c
    return None


def next_number(d, dtype):
    b = d["business"]
    prefixes = {"invoice": b.get("inv_prefix") or "INV",
                "estimate": b.get("est_prefix") or "EST",
                "receipt": b.get("rec_prefix") or "REC"}
    n = d["counters"].get(dtype, 0) + 1
    d["counters"][dtype] = n
    return "%s%04d" % (prefixes.get(dtype, "DOC"), n)


def fmt_date(date_str, date_format="DD Mon YYYY"):
    """Format an ISO date per the business date-format setting."""
    if not date_str:
        return ""
    try:
        dt = datetime.date.fromisoformat(str(date_str)[:10])
    except ValueError:
        return str(date_str)
    fmt = date_format or "DD Mon YYYY"
    if fmt == "DD-MM-YYYY":
        return dt.strftime("%d-%m-%Y")
    if fmt == "YYYY-MM-DD":
        return dt.strftime("%Y-%m-%d")
    if fmt == "Mon DD, YYYY":
        return dt.strftime("%b %d, %Y")
    return dt.strftime("%d %b %Y")


def share_message(d, doc, share_url):
    """Fill the business email/share template for a document."""
    biz = d["business"]
    cur = biz.get("currency", "MMK")
    client = find_client(d, doc.get("client_id")) or {}
    tpl = biz.get("default_email_message") or ""
    return (tpl.replace("{client}", client.get("name") or "")
               .replace("{type}", TYPE_TITLES.get(doc.get("type"), "Document"))
               .replace("{number}", doc.get("number", ""))
               .replace("{total}", fmt_money(doc_totals(doc)["total"], cur))
               .replace("{business}", biz.get("name") or "")
               .replace("{link}", share_url))


def _add_months(date_str, n):
    dt = datetime.date.fromisoformat(date_str)
    m = dt.month - 1 + n
    y = dt.year + m // 12
    m = m % 12 + 1
    import calendar
    day = min(dt.day, calendar.monthrange(y, m)[1])
    return datetime.date(y, m, day).isoformat()


def _run_recurring(d):
    """Generate documents for due recurring templates. Returns changed."""
    import copy
    changed = False
    today = today_str()
    for r in d.setdefault("recurring", []):
        if not r.get("active"):
            continue
        tpl = find_doc(d, r.get("doc_id"))
        if not tpl:
            continue
        while r.get("next_date") and r["next_date"] <= today:
            issue = r["next_date"]
            due = ""
            if tpl.get("issue_date") and tpl.get("due_date"):
                try:
                    delta = (datetime.date.fromisoformat(tpl["due_date"]) -
                             datetime.date.fromisoformat(tpl["issue_date"])).days
                    due = (datetime.date.fromisoformat(issue) +
                           datetime.timedelta(days=delta)).isoformat()
                except ValueError:
                    due = ""
            doc = copy.deepcopy(tpl)
            doc["id"] = secrets.token_hex(8)
            doc["number"] = next_number(d, doc["type"])
            doc["issue_date"] = issue
            doc["due_date"] = due
            doc["status"] = "paid" if doc["type"] == "receipt" else "draft"
            doc["paid_at"] = now_iso() if doc["status"] == "paid" else None
            doc["share_token"] = secrets.token_urlsafe(16)
            doc["created_at"] = now_iso()
            d["documents"].append(doc)
            r["next_date"] = _add_months(r["next_date"], 1)
            changed = True
    return changed


def month_key(date_str):
    return (date_str or "")[:7]


# ------------------------------------------------------------- invoices tab

@app.route("/")
def home():
    email = require_user()
    d = user_data(email)
    if _run_recurring(d):
        save_all()
    b = d["business"]
    cur = b.get("currency", "MMK")
    dformat = b.get("date_format", "DD-MM-YYYY")

    tab = request.args.get("tab") or "all"
    if tab not in ("all", "outstanding", "paid"):
        tab = "all"
    q = (request.args.get("q") or "").strip().lower()

    invs = [doc for doc in d["documents"] if doc.get("type") == "invoice"]
    years = {}
    for doc in sorted(invs, key=lambda x: (x.get("issue_date") or "",
                                           x.get("created_at", "")),
                      reverse=True):
        st = eff_status(doc)
        if tab == "outstanding" and st not in ("draft", "sent", "overdue"):
            continue
        if tab == "paid" and st != "paid":
            continue
        if q:
            c = find_client(d, doc.get("client_id")) or {}
            hay = " ".join([doc.get("number", ""), c.get("name", ""),
                            c.get("company", "")]).lower()
            if q not in hay:
                continue
        total = doc_totals(doc)["total"]
        year = (doc.get("issue_date") or "")[:4] or "—"
        years.setdefault(year, {"rows": [], "total": 0.0})
        years[year]["rows"].append((doc, total, st))
        years[year]["total"] += total
    ordered = sorted(years.items(), reverse=True)
    return render_template("invoices.html", email=email, biz=b,
                           years=ordered, tab=tab, q=request.args.get("q", ""),
                           fmt_money=fmt_money, fmt_date=fmt_date,
                           cur=cur, dformat=dformat, statuses=STATUS_LABELS,
                           clients=d["clients"], activetab="invoices")


@app.route("/estimates")
def estimates():
    email = require_user()
    d = user_data(email)
    if _run_recurring(d):
        save_all()
    b = d["business"]
    cur = b.get("currency", "MMK")
    dformat = b.get("date_format", "DD-MM-YYYY")
    tab = request.args.get("tab") or "all"
    if tab not in ("all", "pending", "accepted"):
        tab = "all"
    q = (request.args.get("q") or "").strip().lower()
    ests = [doc for doc in d["documents"] if doc.get("type") == "estimate"]
    years = {}
    for doc in sorted(ests, key=lambda x: (x.get("issue_date") or "",
                                           x.get("created_at", "")),
                      reverse=True):
        st = eff_status(doc)
        if tab == "pending" and st not in ("draft", "sent"):
            continue
        if tab == "accepted" and st != "accepted":
            continue
        if q:
            c = find_client(d, doc.get("client_id")) or {}
            hay = " ".join([doc.get("number", ""), c.get("name", ""),
                            c.get("company", "")]).lower()
            if q not in hay:
                continue
        total = doc_totals(doc)["total"]
        year = (doc.get("issue_date") or "")[:4] or "—"
        years.setdefault(year, {"rows": [], "total": 0.0})
        years[year]["rows"].append((doc, total, st))
        years[year]["total"] += total
    ordered = sorted(years.items(), reverse=True)
    return render_template("estimates.html", email=email, biz=b,
                           years=ordered, tab=tab, q=request.args.get("q", ""),
                           fmt_money=fmt_money, fmt_date=fmt_date,
                           cur=cur, dformat=dformat, statuses=STATUS_LABELS,
                           clients=d["clients"], activetab="estimates")


@app.route("/receipts")
def receipts():
    email = require_user()
    d = user_data(email)
    b = d["business"]
    cur = b.get("currency", "MMK")
    dformat = b.get("date_format", "DD-MM-YYYY")
    recs = [doc for doc in d["documents"] if doc.get("type") == "receipt"]
    recs.sort(key=lambda x: (x.get("issue_date") or "",
                              x.get("created_at", "")), reverse=True)
    rows = [(doc, doc_totals(doc)["total"], eff_status(doc)) for doc in recs]
    client_names = {c["id"]: c["name"] for c in d["clients"]}
    return render_template("receipts.html", email=email, biz=b, rows=rows,
                           fmt_money=fmt_money, fmt_date=fmt_date,
                           cur=cur, dformat=dformat, statuses=STATUS_LABELS,
                           client_names=client_names, activetab="more")


# ------------------------------------------------------------- doc editor

def _parse_doc_form(d):
    b = d["business"]
    dtype = request.form.get("type") or "invoice"
    if dtype not in ("invoice", "estimate", "receipt"):
        dtype = "invoice"
    desc = request.form.getlist("desc")
    qty = request.form.getlist("qty")
    rate = request.form.getlist("rate")
    tax_pct = request.form.getlist("tax_pct")
    lines = []
    for i, ds in enumerate(desc):
        ds = (ds or "").strip()
        q = parse_num(qty[i] if i < len(qty) else 0)
        r = parse_num(rate[i] if i < len(rate) else 0)
        if not ds and q == 0 and r == 0:
            continue
        lines.append({"desc": ds, "qty": q, "rate": r,
                      "tax_pct": parse_num(tax_pct[i] if i < len(tax_pct) else 0)})
    # client: pick existing or create inline
    client_id = request.form.get("client_id") or ""
    if client_id == "__new__":
        name = (request.form.get("new_client_name") or "").strip()
        if name:
            c = {"id": secrets.token_hex(6), "name": name,
                 "company": (request.form.get("new_client_company") or "").strip(),
                 "email": (request.form.get("new_client_email") or "").strip(),
                 "phone": (request.form.get("new_client_phone") or "").strip(),
                 "address": (request.form.get("new_client_address") or "").strip()}
            d["clients"].append(c)
            client_id = c["id"]
        else:
            client_id = ""
    elif not find_client(d, client_id):
        client_id = ""
    return {
        "type": dtype, "client_id": client_id, "lines": lines,
        "issue_date": request.form.get("issue_date") or today_str(),
        "due_date": request.form.get("due_date") or "",
        "discount_type": request.form.get("discount_type") or "amount",
        "discount_value": parse_num(request.form.get("discount_value")),
        "tax_type": request.form.get("tax_type") or "percent",
        "tax_value": parse_num(request.form.get("tax_value") or b.get("default_tax")),
        "shipping": parse_num(request.form.get("shipping")),
        "notes": (request.form.get("notes") or "").strip(),
        "terms": (request.form.get("terms") or "").strip(),
    }


def _default_doc(d, dtype):
    b = d["business"]
    return {
        "type": dtype, "number": "", "issue_date": today_str(),
        "due_date": "", "client_id": "",
        "lines": [{"desc": "", "qty": 1, "rate": 0, "tax_pct": 0}],
        "discount_type": "amount", "discount_value": 0,
        "tax_type": "percent", "tax_value": b.get("default_tax") or 0,
        "shipping": 0,
        "notes": b.get("default_notes") or "",
        "terms": b.get("default_terms") or "",
    }


@app.route("/docs/new", methods=["GET", "POST"])
def doc_new():
    email = require_user()
    d = user_data(email)
    dtype = request.args.get("type") or "invoice"
    if dtype not in ("invoice", "estimate", "receipt"):
        dtype = "invoice"
    if request.method == "POST":
        fields = _parse_doc_form(d)
        status = "paid" if fields["type"] == "receipt" else "draft"
        doc = {"id": secrets.token_hex(8),
               "number": next_number(d, fields["type"]),
               "status": status,
               "share_token": secrets.token_urlsafe(16),
               "created_at": now_iso(),
               "paid_at": now_iso() if status == "paid" else None}
        doc.update(fields)
        d["documents"].append(doc)
        save_all()
        return redirect("/docs/" + doc["id"])
    return render_template("doc_editor.html", email=email, biz=d["business"],
                           doc=_default_doc(d, dtype), clients=d["clients"],
                           items=d["items"], mode="new", edit_id=None,
                           cur=d["business"].get("currency", "MMK"),
                           currencies=CURRENCIES,
                           activetab={"invoice": "invoices",
                                      "estimate": "estimates"}.get(dtype,
                                                                   "more"))


@app.route("/docs/<doc_id>/edit", methods=["GET", "POST"])
def doc_edit(doc_id):
    email = require_user()
    d = user_data(email)
    doc = find_doc(d, doc_id)
    if not doc:
        abort(404)
    if request.method == "POST":
        dtype = request.form.get("type") or doc["type"]
        if dtype not in ("invoice", "estimate", "receipt"):
            dtype = doc["type"]
        fields = _parse_doc_form(d)
        fields["type"] = dtype
        if dtype == "receipt" and doc.get("status") != "paid":
            fields["status"] = "paid"
            fields["paid_at"] = now_iso()
        else:
            fields["status"] = doc.get("status", "draft")
            fields["paid_at"] = doc.get("paid_at")
        doc.update(fields)
        save_all()
        return redirect("/docs/" + doc["id"])
    ed = dict(doc)
    ed["lines"] = [dict(l) for l in doc.get("lines", [])] or \
        [{"desc": "", "qty": 1, "rate": 0, "tax_pct": 0}]
    return render_template("doc_editor.html", email=email, biz=d["business"],
                           doc=ed, clients=d["clients"], items=d["items"],
                           mode="edit", edit_id=doc_id,
                           cur=d["business"].get("currency", "MMK"),
                           currencies=CURRENCIES,
                           activetab={"invoice": "invoices",
                                      "estimate": "estimates"}.get(
                                          ed.get("type"), "more"))


# ---------------------------------------------------------- doc actions

@app.route("/docs/<doc_id>")
def doc_detail(doc_id):
    email = require_user()
    d = user_data(email)
    doc = find_doc(d, doc_id)
    if not doc:
        abort(404)
    client = find_client(d, doc.get("client_id")) or {}
    totals = doc_totals(doc)
    share_url = request.host_url.rstrip("/") + "/s/" + doc.get("share_token", "")
    from urllib.parse import quote
    msg = share_message(d, doc, share_url)
    wa_url = "https://wa.me/?text=" + quote(msg)
    mail_url = ("mailto:?subject=" + quote(
        "%s %s from %s" % (TYPE_TITLES.get(doc["type"], "Document"),
                           doc.get("number", ""),
                           d["business"].get("name") or "Invoice Maker")) +
        "&body=" + quote(msg))
    return render_template("doc_detail.html", email=email, biz=d["business"],
                           doc=doc, client=client, totals=totals,
                           status=eff_status(doc), share_url=share_url,
                           wa_url=wa_url, mail_url=mail_url,
                           fmt_money=fmt_money, fmt_date=fmt_date,
                           dformat=d["business"].get("date_format",
                                                     "DD-MM-YYYY"),
                           cur=d["business"].get("currency", "MMK"),
                           statuses=STATUS_LABELS,
                           type_titles=TYPE_TITLES,
                           activetab={"invoice": "invoices",
                                      "estimate": "estimates"}.get(
                                          doc.get("type"), "more"))


@app.route("/docs/<doc_id>/mark", methods=["POST"])
def doc_mark(doc_id):
    email = require_user()
    d = user_data(email)
    doc = find_doc(d, doc_id)
    if not doc:
        abort(404)
    action = request.form.get("action") or ""
    dtype = doc.get("type")
    allowed = {"invoice": {"sent", "draft", "paid", "cancelled"},
               "estimate": {"sent", "draft", "accepted", "declined",
                            "expired"},
               "receipt": {"paid"}}
    if action in allowed.get(dtype, set()):
        doc["status"] = action
        doc["paid_at"] = now_iso() if action == "paid" else None
        save_all()
    return redirect("/docs/" + doc_id)


@app.route("/docs/<doc_id>/duplicate", methods=["POST"])
def doc_duplicate(doc_id):
    email = require_user()
    d = user_data(email)
    doc = find_doc(d, doc_id)
    if not doc:
        abort(404)
    import copy
    dup = copy.deepcopy(doc)
    dup["id"] = secrets.token_hex(8)
    dup["number"] = next_number(d, dup["type"])
    dup["issue_date"] = today_str()
    dup["status"] = "paid" if dup["type"] == "receipt" else "draft"
    dup["paid_at"] = now_iso() if dup["status"] == "paid" else None
    dup["share_token"] = secrets.token_urlsafe(16)
    dup["created_at"] = now_iso()
    d["documents"].append(dup)
    save_all()
    return redirect("/docs/" + dup["id"])


@app.route("/docs/<doc_id>/convert", methods=["POST"])
def doc_convert(doc_id):
    """Convert an estimate into a new invoice."""
    email = require_user()
    d = user_data(email)
    doc = find_doc(d, doc_id)
    if not doc or doc.get("type") != "estimate":
        abort(404)
    import copy
    inv = copy.deepcopy(doc)
    inv["id"] = secrets.token_hex(8)
    inv["type"] = "invoice"
    inv["number"] = next_number(d, "invoice")
    inv["status"] = "draft"
    inv["paid_at"] = None
    inv["issue_date"] = today_str()
    inv["share_token"] = secrets.token_urlsafe(16)
    inv["created_at"] = now_iso()
    d["documents"].append(inv)
    doc["status"] = "accepted"
    save_all()
    return redirect("/docs/" + inv["id"])


@app.route("/docs/<doc_id>/delete", methods=["POST"])
def doc_delete(doc_id):
    email = require_user()
    d = user_data(email)
    d["documents"] = [x for x in d["documents"] if x["id"] != doc_id]
    save_all()
    return redirect("/")


# ------------------------------------------------------------------ pdf

def _hex_to_rgb(h):
    h = (h or "").strip().lstrip("#")
    try:
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except (ValueError, IndexError):
        return (37, 99, 235)


def render_doc_pdf(d, doc):
    """Build the invoice PDF bytes (fpdf2, with Thai/Myanmar fallback fonts)."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    biz = d["business"]
    cur = biz.get("currency", "MMK")
    accent = _hex_to_rgb(biz.get("accent_color"))
    title = TYPE_TITLES.get(doc.get("type"), "Document").upper()
    client = find_client(d, doc.get("client_id")) or {}
    totals = doc_totals(doc)

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=25)
    try:
        pdf.set_text_shaping(True)
    except Exception as e:
        print("text shaping unavailable:", e, flush=True)
    pdf.add_font("ns", "", os.path.join(FONTS_DIR, "NotoSans-Regular.ttf"))
    pdf.add_font("ns", "B", os.path.join(FONTS_DIR, "NotoSans-Bold.ttf"))
    pdf.add_font("nst", "", os.path.join(FONTS_DIR, "NotoSansThai-Regular.ttf"))
    pdf.add_font("padauk", "", os.path.join(FONTS_DIR, "Padauk-Regular.ttf"))
    pdf.set_fallback_fonts(["nst", "padauk"], exact_match=False)
    pdf.set_margins(12, 12, 12)
    pdf.add_page()
    W = 210 - 24  # printable width

    # accent header bar
    pdf.set_fill_color(*accent)
    pdf.rect(0, 0, 210, 30, "F")
    logo = biz.get("logo_path") or ""
    logo_file = os.path.join(DATA_DIR, logo) if logo else ""
    if logo_file and os.path.isfile(logo_file):
        try:
            pdf.image(logo_file, x=210 - 12 - 28, y=5, w=28)
        except Exception as e:
            print("logo embed failed:", e, flush=True)
    pdf.set_xy(12, 9)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("ns", "B", 17)
    seller = (biz.get("name") or "").strip()
    doc_title = TYPE_TITLES.get(doc.get("type"), "Document")
    banner = "%s By %s" % (doc_title, seller) if seller else doc_title
    pdf.cell(150, 9, banner, new_x=XPos.LMARGIN,
             new_y=YPos.NEXT)
    pdf.set_x(12)
    pdf.set_font("ns", "", 9)
    pdf.set_text_color(230, 230, 230)
    biz_line = "  ".join(x for x in [biz.get("email"), biz.get("phone")]
                         if x)
    if biz_line:
        pdf.cell(150, 5, biz_line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    biz_addr = (biz.get("address") or "").strip()
    if biz_addr:
        pdf.set_x(12)
        pdf.multi_cell(150, 5, biz_addr, new_x=XPos.LMARGIN,
                       new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)

    y = 38
    pdf.set_xy(12, y)
    pdf.set_text_color(*accent)
    pdf.set_font("ns", "B", 24)
    pdf.cell(0, 10, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(12)
    pdf.set_text_color(110, 110, 110)
    pdf.set_font("ns", "", 12)
    pdf.cell(0, 7, doc.get("number", ""), new_x=XPos.LMARGIN,
             new_y=YPos.NEXT)

    # dates block (right)
    pdf.set_xy(130, y)
    pdf.set_font("ns", "", 10)
    pdf.set_text_color(110, 110, 110)
    pdf.cell(30, 6, "Issue date:", align="R")
    pdf.set_text_color(0, 0, 0)
    pdf.cell(38, 6, fmt_date(doc.get("issue_date", ""), biz.get("date_format")),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
    pdf.set_x(130)
    pdf.set_text_color(110, 110, 110)
    pdf.cell(30, 6, "Due date:", align="R")
    pdf.set_text_color(0, 0, 0)
    pdf.cell(38, 6, fmt_date(doc.get("due_date") or "", biz.get("date_format")) or "-",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
    if doc.get("type") == "invoice":
        pdf.set_x(130)
        pdf.set_text_color(110, 110, 110)
        pdf.cell(30, 6, "Status:", align="R")
        pdf.set_text_color(0, 0, 0)
        pdf.cell(38, 6, STATUS_LABELS.get(eff_status(doc), ""),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")

    y = max(pdf.get_y(), y + 22) + 4
    pdf.set_xy(12, y)
    pdf.set_text_color(110, 110, 110)
    pdf.set_font("ns", "B", 10)
    pdf.cell(0, 6, "BILL TO", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("ns", "B", 12)
    pdf.set_x(12)
    cname = client.get("name") or client.get("company") or "-"
    pdf.cell(0, 7, cname, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("ns", "", 10)
    for key in ("company", "address", "email", "phone"):
        v = (client.get(key) or "").strip()
        if v and not (key == "company" and v == cname):
            pdf.set_x(12)
            pdf.multi_cell(100, 5.5, v, new_x=XPos.LMARGIN,
                           new_y=YPos.NEXT)

    y = pdf.get_y() + 6

    # line items table
    cw = [W - 76, 18, 29, 29]  # desc, qty, rate, amount
    xs = [12]
    for w in cw[:-1]:
        xs.append(xs[-1] + w)

    def table_header(yy):
        pdf.set_xy(12, yy)
        pdf.set_fill_color(243, 244, 246)
        pdf.set_font("ns", "B", 10)
        pdf.set_text_color(60, 60, 60)
        for i, head in enumerate(("Description", "Qty", "Rate", "Amount")):
            align = "L" if i == 0 else ("C" if i == 1 else "R")
            pdf.set_xy(xs[i], yy)
            pdf.cell(cw[i], 8, head, border=1, fill=True, align=align,
                     new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_xy(12, yy + 8)
        return yy + 8

    y = table_header(y)
    pdf.set_font("ns", "", 10)
    pdf.set_text_color(0, 0, 0)
    lines = doc.get("lines") or []
    if not lines:
        pdf.set_xy(12, y)
        pdf.cell(W, 8, "-", border=1, align="C")
        y += 8
    for ln in lines:
        desc = ln.get("desc") or ""
        qty_s = ("%g" % parse_num(ln.get("qty")))
        rate_s = fmt_money(ln.get("rate"), cur)
        amt_s = fmt_money(parse_num(ln.get("qty")) * parse_num(ln.get("rate")),
                          cur)
        # measure description height
        try:
            nlines = pdf.multi_cell(cw[0], 6, desc or " ", dry_run=True,
                                    output="LINES")
            rh = max(8, len(nlines) * 6)
        except Exception:
            rh = 8
        if y + rh > 265:
            pdf.add_page()
            y = table_header(pdf.get_y())
        y0 = y
        pdf.set_xy(xs[0], y0)
        pdf.multi_cell(cw[0], 6, desc or " ", border=0,
                       new_x=XPos.RIGHT, new_y=YPos.TOP)
        h = max(rh, pdf.get_y() - y0)
        for i, (txt, align) in enumerate(((qty_s, "C"), (rate_s, "R"),
                                         (amt_s, "R")), start=1):
            pdf.set_xy(xs[i], y0)
            pdf.multi_cell(cw[i], h, txt, border=0, align=align,
                           new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.rect(12, y0, W, h)
        for i in range(1, 4):
            pdf.line(xs[i], y0, xs[i], y0 + h)
        y = y0 + h

    # totals
    y += 4
    pdf.set_font("ns", "", 10)
    total_rows = [("Subtotal", fmt_money(totals["subtotal"], cur))]
    if totals["discount"]:
        total_rows.append(("Discount", "-" + fmt_money(totals["discount"], cur)))
    if totals["tax"]:
        total_rows.append(("Tax", fmt_money(totals["tax"], cur)))
    if totals["line_tax"]:
        total_rows.append(("Item tax", fmt_money(totals["line_tax"], cur)))
    if totals["shipping"]:
        total_rows.append(("Shipping", fmt_money(totals["shipping"], cur)))
    for label, val in total_rows:
        pdf.set_xy(110, y)
        pdf.cell(45, 6.5, label, align="R")
        pdf.cell(43, 6.5, val, align="R", new_x=XPos.LMARGIN,
                 new_y=YPos.NEXT)
        y += 6.5
    pdf.set_xy(110, y)
    pdf.set_fill_color(accent[0], accent[1], accent[2])
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("ns", "B", 12)
    pdf.cell(45, 9, "Total", align="R", fill=True)
    pdf.cell(43, 9, fmt_money(totals["total"], cur), align="R", fill=True,
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    y += 12

    if biz.get("payment_details"):
        if y > 245:
            pdf.add_page()
            y = pdf.get_y()
        pdf.set_xy(12, y)
        pdf.set_font("ns", "B", 10)
        pdf.cell(0, 6, "Payment details", new_x=XPos.LMARGIN,
                 new_y=YPos.NEXT)
        pdf.set_x(12)
        pdf.set_font("ns", "", 10)
        pdf.multi_cell(0, 5.5, biz["payment_details"],
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        y = pdf.get_y() + 3

    for label, key in (("Notes", "notes"), ("Terms", "terms")):
        if doc.get(key):
            if y > 245:
                pdf.add_page()
                y = pdf.get_y()
            pdf.set_xy(12, y)
            pdf.set_font("ns", "B", 10)
            pdf.cell(0, 6, label, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_x(12)
            pdf.set_font("ns", "", 10)
            pdf.multi_cell(0, 5.5, doc[key], new_x=XPos.LMARGIN,
                           new_y=YPos.NEXT)
            y = pdf.get_y() + 3

    # signature
    sig = biz.get("signature_path") or ""
    sig_file = os.path.join(DATA_DIR, sig) if sig else ""
    if sig_file and os.path.isfile(sig_file):
        if y + 30 > 270:
            pdf.add_page()
            y = pdf.get_y()
        pdf.set_xy(12, y)
        try:
            pdf.image(sig_file, x=12, y=y, w=45)
        except Exception as e:
            print("signature embed failed:", e, flush=True)
        y += 22
        pdf.set_xy(12, y)
        pdf.set_font("ns", "", 9)
        pdf.set_text_color(110, 110, 110)
        pdf.cell(60, 5, "Authorized signature",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_x(12)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(60, 5, biz.get("name") or "")

    pdf.set_y(-15)
    pdf.set_font("ns", "", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 10, "Page %d/{nb}" % pdf.page_no(), align="C")
    return bytes(pdf.output())


@app.route("/docs/<doc_id>/pdf")
def doc_pdf(doc_id):
    email = require_user()
    d = user_data(email)
    doc = find_doc(d, doc_id)
    if not doc:
        abort(404)
    try:
        data = render_doc_pdf(d, doc)
    except Exception:
        import traceback
        traceback.print_exc()
        return ("Sorry — the PDF couldn't be created. "
                "Please try again."), 500
    fname = "%s.pdf" % (doc.get("number") or "document")
    return send_file(io.BytesIO(data), mimetype="application/pdf",
                     as_attachment=True, download_name=fname)


@app.route("/s/<token>")
def public_view(token):
    for email, d in invdata.items():
        doc = find_doc_by_token(d, token)
        if doc:
            client = find_client(d, doc.get("client_id")) or {}
            return render_template("public.html", biz=d["business"],
                                   doc=doc, client=client,
                                   totals=doc_totals(doc),
                                   status=eff_status(doc),
                                   fmt_money=fmt_money,
                                   cur=d["business"].get("currency", "MMK"),
                                   statuses=STATUS_LABELS,
                                   type_titles=TYPE_TITLES)
    abort(404)


@app.route("/s/<token>/pdf")
def public_pdf(token):
    """Shared-link PDF download — no account needed."""
    for email, d in invdata.items():
        doc = find_doc_by_token(d, token)
        if doc:
            try:
                data = render_doc_pdf(d, doc)
            except Exception:
                import traceback
                traceback.print_exc()
                return ("Sorry — the PDF couldn't be created. "
                        "Please try again."), 500
            fname = "%s.pdf" % (doc.get("number") or "document")
            return send_file(io.BytesIO(data), mimetype="application/pdf",
                             as_attachment=True, download_name=fname)
    abort(404)


# ------------------------------------------------- clients / items / expenses

@app.route("/clients", methods=["GET", "POST"])
def clients():
    email = require_user()
    d = user_data(email)
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if name:
            d["clients"].append({
                "id": secrets.token_hex(6), "name": name,
                "company": (request.form.get("company") or "").strip(),
                "email": (request.form.get("email") or "").strip(),
                "phone": (request.form.get("phone") or "").strip(),
                "address": (request.form.get("address") or "").strip()})
            save_all()
        return redirect("/clients")
    return render_template("clients.html", email=email, biz=d["business"],
                           clients=d["clients"], activetab="more")


@app.route("/clients/<cid>/delete", methods=["POST"])
def client_delete(cid):
    email = require_user()
    d = user_data(email)
    d["clients"] = [c for c in d["clients"] if c["id"] != cid]
    save_all()
    return redirect("/clients")


@app.route("/items", methods=["GET", "POST"])
def items():
    email = require_user()
    d = user_data(email)
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if name:
            d["items"].append({
                "id": secrets.token_hex(6), "name": name,
                "description": (request.form.get("description") or "").strip(),
                "rate": parse_num(request.form.get("rate"))})
            save_all()
        return redirect("/items")
    return render_template("items.html", email=email, biz=d["business"],
                           items=d["items"], fmt_money=fmt_money,
                           cur=d["business"].get("currency", "MMK"),
                           activetab="more")


@app.route("/items/<iid>/delete", methods=["POST"])
def item_delete(iid):
    email = require_user()
    d = user_data(email)
    d["items"] = [i for i in d["items"] if i["id"] != iid]
    save_all()
    return redirect("/items")


@app.route("/expenses", methods=["GET", "POST"])
def expenses():
    email = require_user()
    d = user_data(email)
    if request.method == "POST":
        amount = parse_num(request.form.get("amount"))
        if amount > 0:
            d["expenses"].append({
                "id": secrets.token_hex(6),
                "date": request.form.get("date") or today_str(),
                "category": (request.form.get("category") or "").strip(),
                "vendor": (request.form.get("vendor") or "").strip(),
                "amount": amount,
                "note": (request.form.get("note") or "").strip()})
            save_all()
        return redirect("/expenses")
    exp = sorted(d["expenses"], key=lambda e: e.get("date", ""),
                 reverse=True)
    total = sum(parse_num(e.get("amount")) for e in d["expenses"])
    return render_template("expenses.html", email=email, biz=d["business"],
                           expenses=exp, total=total, fmt_money=fmt_money,
                           cur=d["business"].get("currency", "MMK"),
                           today=today_str(), activetab="expenses")


@app.route("/expenses/<eid>/delete", methods=["POST"])
def expense_delete(eid):
    email = require_user()
    d = user_data(email)
    d["expenses"] = [e for e in d["expenses"] if e["id"] != eid]
    save_all()
    return redirect("/expenses")


# ---------------------------------------------------------------- settings

def _user_upload_dir(email):
    safe = re.sub(r"[^a-z0-9]+", "_", email.lower())
    path = os.path.join(UPLOADS_DIR, safe)
    os.makedirs(path, exist_ok=True)
    return path


def _store_image_upload(f, dest_dir, name):
    """Validate with PIL and store an uploaded image. Returns rel path."""
    from PIL import Image
    raw = f.read()
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("Image is larger than 2 MB.")
    img = Image.open(io.BytesIO(raw))
    img.verify()
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    dest = os.path.join(dest_dir, name)
    img.save(dest, "PNG")
    return os.path.join("uploads", os.path.basename(dest_dir), name)


def _valid_accent(v):
    v = (v or "").strip()
    if re.fullmatch(r"#?[0-9a-fA-F]{3}([0-9a-fA-F]{3})?", v):
        return v if v.startswith("#") else "#" + v
    return None


TEMPLATE_PRESETS = [("Blue", "#2563eb"), ("Indigo", "#4f46e5"),
                    ("Green", "#059669")]


@app.route("/settings")
def settings():
    email = require_user()
    d = user_data(email)
    return render_template("settings.html", email=email, biz=d["business"],
                           activetab="more")


@app.route("/settings/business", methods=["GET", "POST"])
def settings_business():
    email = require_user()
    d = user_data(email)
    b = d["business"]
    msg = None
    if request.method == "POST":
        for k in ("name", "address", "email", "phone", "website", "tax_id"):
            b[k] = (request.form.get(k) or "").strip()
        try:
            udir = _user_upload_dir(email)
            logo = request.files.get("logo")
            if logo and logo.filename:
                ext = (logo.filename.rsplit(".", 1)[-1] or "").lower()
                if ext not in ("png", "jpg", "jpeg"):
                    raise ValueError("Logo must be a PNG or JPG file.")
                b["logo_path"] = _store_image_upload(logo, udir, "logo.png")
            if request.form.get("remove_logo"):
                b["logo_path"] = ""
            msg = "Business details saved."
        except ValueError as e:
            msg = "Error: %s" % e
        save_all()
    return render_template("set_business.html", email=email, biz=b, msg=msg,
                           activetab="more")


@app.route("/settings/template", methods=["GET", "POST"])
def settings_template():
    email = require_user()
    d = user_data(email)
    b = d["business"]
    msg = None
    if request.method == "POST":
        preset = request.form.get("preset") or ""
        custom = _valid_accent(request.form.get("custom_color"))
        if preset in [p[1] for p in TEMPLATE_PRESETS]:
            b["accent_color"] = preset
            msg = "Template updated."
        elif custom:
            b["accent_color"] = custom
            msg = "Template updated."
        save_all()
    return render_template("set_template.html", email=email, biz=b, msg=msg,
                           presets=TEMPLATE_PRESETS, activetab="more")


@app.route("/settings/payments", methods=["GET", "POST"])
def settings_payments():
    email = require_user()
    d = user_data(email)
    b = d["business"]
    msg = None
    if request.method == "POST":
        b["payment_details"] = (request.form.get("payment_details") or "").strip()
        msg = "Payment methods saved."
        save_all()
    return render_template("set_payments.html", email=email, biz=b, msg=msg,
                           activetab="more")


@app.route("/settings/tax", methods=["GET", "POST"])
def settings_tax():
    email = require_user()
    d = user_data(email)
    b = d["business"]
    msg = None
    if request.method == "POST":
        b["default_tax"] = parse_num(request.form.get("default_tax"))
        msg = "Default tax rate saved."
        save_all()
    return render_template("set_tax.html", email=email, biz=b, msg=msg,
                           activetab="more")


@app.route("/settings/notes", methods=["GET", "POST"])
def settings_notes():
    email = require_user()
    d = user_data(email)
    b = d["business"]
    msg = None
    if request.method == "POST":
        b["default_notes"] = (request.form.get("default_notes") or "").strip()
        b["default_terms"] = (request.form.get("default_terms") or "").strip()
        msg = "Default notes saved."
        save_all()
    return render_template("set_notes.html", email=email, biz=b, msg=msg,
                           activetab="more")


@app.route("/settings/numbering", methods=["GET", "POST"])
def settings_numbering():
    email = require_user()
    d = user_data(email)
    b = d["business"]
    msg = None
    if request.method == "POST":
        for dtype, pkey in (("invoice", "inv_prefix"), ("estimate", "est_prefix"),
                            ("receipt", "rec_prefix")):
            v = re.sub(r"[^A-Za-z0-9]", "", request.form.get(pkey) or "")
            if v:
                b[pkey] = v[:8].upper()
            try:
                nxt = int(request.form.get("next_" + dtype) or 0)
                if nxt >= 1:
                    d["counters"][dtype] = nxt - 1
            except ValueError:
                pass
        msg = "Numbering settings saved."
        save_all()
    nexts = {t: d["counters"].get(t, 0) + 1
             for t in ("invoice", "estimate", "receipt")}
    preview = {t: "%s%04d" % (b.get({"invoice": "inv_prefix",
                                     "estimate": "est_prefix",
                                     "receipt": "rec_prefix"}[t]), nexts[t])
               for t in nexts}
    return render_template("set_numbering.html", email=email, biz=b, msg=msg,
                           nexts=nexts, preview=preview,
                           type_titles=TYPE_TITLES, activetab="more")


@app.route("/settings/email", methods=["GET", "POST"])
def settings_email():
    email = require_user()
    d = user_data(email)
    b = d["business"]
    msg = None
    if request.method == "POST":
        b["default_email_message"] = request.form.get("default_email_message") or ""
        msg = "Email message saved."
        save_all()
    return render_template("set_email.html", email=email, biz=b, msg=msg,
                           activetab="more")


@app.route("/settings/region", methods=["GET", "POST"])
def settings_region():
    email = require_user()
    d = user_data(email)
    b = d["business"]
    msg = None
    if request.method == "POST":
        cur = request.form.get("currency") or "MMK"
        if cur in CURRENCIES:
            b["currency"] = cur
        df = request.form.get("date_format") or "DD Mon YYYY"
        if df in ("DD Mon YYYY", "Mon DD, YYYY", "DD-MM-YYYY", "YYYY-MM-DD"):
            b["date_format"] = df
            b["_date_fmt_en"] = True  # explicit choice; skip one-time migration
        msg = "Region settings saved."
        save_all()
    return render_template("set_region.html", email=email, biz=b, msg=msg,
                           currencies=CURRENCIES, activetab="more")


@app.route("/settings/signature", methods=["GET", "POST"])
def settings_signature():
    email = require_user()
    d = user_data(email)
    b = d["business"]
    msg = None
    if request.method == "POST":
        try:
            udir = _user_upload_dir(email)
            sig_data = (request.form.get("signature_data") or "").strip()
            if sig_data.startswith("data:image/png;base64,"):
                raw = base64.b64decode(sig_data.split(",", 1)[1])
                if len(raw) > 2 * 1024 * 1024:
                    raise ValueError("Signature image is larger than 2 MB.")
                from PIL import Image
                img = Image.open(io.BytesIO(raw))
                img.verify()
                with open(os.path.join(udir, "signature.png"), "wb") as f:
                    f.write(raw)
                b["signature_path"] = os.path.join(
                    "uploads", os.path.basename(udir), "signature.png")
            if request.form.get("remove_signature"):
                b["signature_path"] = ""
            msg = "Signature saved."
        except ValueError as e:
            msg = "Error: %s" % e
        save_all()
    return render_template("set_signature.html", email=email, biz=b, msg=msg,
                           activetab="more")


@app.route("/settings/contact")
def settings_contact():
    email = require_user()
    d = user_data(email)
    return render_template("set_contact.html", email=email, biz=d["business"],
                           activetab="more")


@app.route("/settings/about")
def settings_about():
    email = require_user()
    d = user_data(email)
    return render_template("set_about.html", email=email, biz=d["business"],
                           version=VERSION, activetab="more")


@app.route("/settings/export/invoices.csv")
def export_invoices_csv():
    email = require_user()
    d = user_data(email)
    b = d["business"]
    cur = b.get("currency", "MMK")
    import csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Number", "Type", "Client", "Issue date", "Due date",
                "Status", "Subtotal", "Discount", "Tax", "Shipping",
                "Total", "Currency"])
    for doc in sorted(d["documents"], key=lambda x: x.get("number", "")):
        c = find_client(d, doc.get("client_id")) or {}
        t = doc_totals(doc)
        w.writerow([doc.get("number"), doc.get("type"),
                    c.get("name") or c.get("company"),
                    doc.get("issue_date"), doc.get("due_date"),
                    eff_status(doc),
                    "%.2f" % t["subtotal"], "%.2f" % t["discount"],
                    "%.2f" % (t["tax"] + t["line_tax"]),
                    "%.2f" % t["shipping"], "%.2f" % t["total"], cur])
    data = buf.getvalue().encode("utf-8-sig")
    return Response(data, mimetype="text/csv",
                    headers={"Content-Disposition":
                             "attachment; filename=invoice-summary.csv"})


@app.route("/settings/export/expenses.csv")
def export_expenses_csv():
    email = require_user()
    d = user_data(email)
    cur = d["business"].get("currency", "MMK")
    import csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Category", "Vendor", "Amount", "Currency", "Note"])
    for e in sorted(d["expenses"], key=lambda x: x.get("date", "")):
        w.writerow([e.get("date"), e.get("category"), e.get("vendor"),
                    "%.2f" % parse_num(e.get("amount")), cur, e.get("note")])
    data = buf.getvalue().encode("utf-8-sig")
    return Response(data, mimetype="text/csv",
                    headers={"Content-Disposition":
                             "attachment; filename=expense-summary.csv"})


@app.route("/settings/backup")
def settings_backup():
    email = require_user()
    d = user_data(email)
    blob = {"app": "Invoice Maker", "version": VERSION,
            "exported_at": now_iso(), "data": d}
    data = json.dumps(blob, ensure_ascii=False, indent=2).encode("utf-8")
    return Response(data, mimetype="application/json",
                    headers={"Content-Disposition":
                             "attachment; filename=invoice-backup-%s.json"
                             % today_str()})


# ---------------------------------------------------------------- reports

@app.route("/reports")
def reports():
    email = require_user()
    d = user_data(email)
    b = d["business"]
    cur = b.get("currency", "MMK")
    months = {}
    for doc in d["documents"]:
        if doc.get("type") != "invoice":
            continue
        m = (doc.get("issue_date") or "")[:7]
        if not m:
            continue
        total = doc_totals(doc)["total"]
        st = eff_status(doc)
        row = months.setdefault(m, {"invoiced": 0.0, "paid": 0.0,
                                    "outstanding": 0.0, "count": 0})
        row["invoiced"] += total
        row["count"] += 1
        if st == "paid":
            row["paid"] += total
        elif st != "cancelled":
            row["outstanding"] += total
    ordered = sorted(months.items(), reverse=True)
    tot_invoiced = sum(r["invoiced"] for _, r in ordered)
    tot_paid = sum(r["paid"] for _, r in ordered)
    tot_out = sum(r["outstanding"] for _, r in ordered)
    exp_total = sum(parse_num(e.get("amount")) for e in d["expenses"])
    return render_template("reports.html", email=email, biz=b,
                           months=ordered, tot_invoiced=tot_invoiced,
                           tot_paid=tot_paid, tot_out=tot_out,
                           exp_total=exp_total, fmt_money=fmt_money,
                           cur=cur, activetab="reports")


@app.route("/more")
def more():
    email = require_user()
    d = user_data(email)
    return render_template("more.html", email=email, biz=d["business"],
                           activetab="more")


# --------------------------------------------------------------- recurring

@app.route("/recurring", methods=["GET", "POST"])
def recurring():
    email = require_user()
    d = user_data(email)
    if request.method == "POST":
        doc_id = request.form.get("doc_id") or ""
        start = request.form.get("start_date") or today_str()
        if find_doc(d, doc_id):
            d["recurring"].append({"id": secrets.token_hex(6),
                                   "doc_id": doc_id, "next_date": start,
                                   "active": True, "created": now_iso()})
            save_all()
        return redirect("/recurring")
    rows = []
    for r in d.get("recurring", []):
        tpl = find_doc(d, r.get("doc_id"))
        rows.append((r, tpl))
    templates = [doc for doc in d["documents"]
                 if doc.get("type") in ("invoice", "estimate")]
    templates.sort(key=lambda x: x.get("number", ""))
    return render_template("recurring.html", email=email, biz=d["business"],
                           rows=rows, templates=templates,
                           fmt_date=fmt_date, today=today_str(),
                           dformat=d["business"].get("date_format",
                                                     "DD-MM-YYYY"),
                           type_titles=TYPE_TITLES, activetab="more")


@app.route("/recurring/<rid>/toggle", methods=["POST"])
def recurring_toggle(rid):
    email = require_user()
    d = user_data(email)
    for r in d.get("recurring", []):
        if r["id"] == rid:
            r["active"] = not r.get("active")
            save_all()
            break
    return redirect("/recurring")


@app.route("/recurring/<rid>/delete", methods=["POST"])
def recurring_delete(rid):
    email = require_user()
    d = user_data(email)
    d["recurring"] = [r for r in d.get("recurring", []) if r["id"] != rid]
    save_all()
    return redirect("/recurring")


# ------------------------------------------------------------------ admin

def admin_ok():
    return session.get("admin") is True


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        if (request.form.get("password") or "") == ADMIN_PASSWORD and ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin")
        return render_template("admin.html", need_login=True,
                               error="Wrong password."), 403
    if not admin_ok():
        return render_template("admin.html", need_login=True)
    def doc_counts(email):
        d = invdata.get(email) or {}
        return (len(d.get("documents", [])), len(d.get("clients", [])),
                len(d.get("expenses", [])))
    user_list = []
    for em, u in sorted(users.items()):
        dc, cc, ec = doc_counts(em)
        user_list.append((em, (u.get("created", "") or "")[:16].replace("T", " "),
                          dc, cc, ec, bool(u.get("disabled"))))
    code_list = [(c, e.get("label", ""), e.get("used_by"),
                  (e.get("used_at") or "")[:16].replace("T", " "),
                  request.host_url.rstrip("/") + "/i/" + c)
                 for c, e in sorted(codes.items())]
    return render_template("admin.html", need_login=False,
                           user_list=user_list, code_list=code_list)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/admin")


@app.route("/admin/codes", methods=["POST"])
def admin_codes():
    if not admin_ok():
        abort(403)
    n = max(1, min(100, int(request.form.get("n") or 1)))
    label = (request.form.get("label") or "").strip()[:60]
    for _ in range(n):
        c = make_code()
        codes[c] = {"label": label, "used_by": None, "used_at": None,
                    "created": now_iso()}
    save_all()
    return redirect("/admin")


@app.route("/admin/revoke/<code>", methods=["POST"])
def admin_revoke(code):
    if not admin_ok():
        abort(403)
    codes.pop((code or "").strip().upper(), None)
    save_all()
    return redirect("/admin")


@app.route("/admin/users/toggle", methods=["POST"])
def admin_user_toggle():
    if not admin_ok():
        abort(403)
    email = (request.form.get("email") or "").strip().lower()
    u = users.get(email)
    if u:
        u["disabled"] = not u.get("disabled")
        if u["disabled"]:
            for sid in [s for s, e in sessions.items()
                        if e.get("user") == email]:
                sessions.pop(sid, None)
        save_all()
    return redirect("/admin")


@app.route("/admin/users/delete", methods=["POST"])
def admin_user_delete():
    if not admin_ok():
        abort(403)
    email = (request.form.get("email") or "").strip().lower()
    if email in users:
        users.pop(email, None)
        invdata.pop(email, None)
        for sid in [s for s, e in sessions.items()
                    if e.get("user") == email]:
            sessions.pop(sid, None)
        save_all()
    return redirect("/admin")


# ------------------------------------------------------------------ misc

@app.route("/uploads/<path:fname>")
def uploaded_file(fname):
    email = current_user()
    if not email:
        abort(401)
    # only allow files inside this user's upload dir
    safe_user = re.sub(r"[^a-z0-9]+", "_", email.lower())
    if ".." in fname or not fname.startswith("uploads/"):
        abort(404)
    parts = fname.split("/")
    if len(parts) != 3 or parts[1] != safe_user:
        abort(404)
    path = os.path.join(DATA_DIR, fname)
    if not os.path.isfile(path):
        abort(404)
    return send_file(path)


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "version": VERSION})


if __name__ == "__main__":
    if not ADMIN_PASSWORD:
        print("WARNING: ADMIN_PASSWORD is not set — /admin will stay locked.")
    app.run(host="0.0.0.0", port=PORT)
