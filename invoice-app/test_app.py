"""Full test of the Invoice Maker app via Flask test client."""
import io, os, re, sys, tempfile, shutil

os.environ["ADMIN_PASSWORD"] = "testadmin"
tmpd = tempfile.mkdtemp(prefix="invtest_")
os.environ["DATA_DIR"] = tmpd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as A

A.app.config["TESTING"] = True
c = A.app.test_client()
passed, failed = [], []

def check(name, cond, extra=""):
    (passed if cond else failed).append(name)
    print(("PASS " if cond else "FAIL ") + name + (" — " + extra if extra and not cond else ""))

def login_admin():
    r = c.post("/admin", data={"password": "testadmin"}, follow_redirects=True)
    return r.status_code == 200 and b"Invite codes" in r.data

check("healthz", c.get("/healthz").json == {"ok": True, "version": "1.0"})
check("admin login", login_admin())

# create invite code
r = c.post("/admin/codes", data={"n": 1, "label": "test"}, follow_redirects=True)
codes = list(A.codes.keys())
check("admin creates code", len(codes) == 1, f"codes={codes}")
code = codes[0]
c.get("/admin/logout")

# invite link = instant access, no signup form
r = c.get("/i/" + code, follow_redirects=False)
check("invite link signs in instantly", r.status_code == 302
      and r.headers["Location"].startswith("/settings"))
check("code marked used by invite account",
      A.codes[code].get("used_by") == "invite-" + code)
check("invite account created", ("invite-" + code) in A.users
      and A.users["invite-" + code].get("kind") == "invite")

# opening the same link in a fresh browser signs back into the same account
c3 = A.app.test_client()
r = c3.get("/i/" + code, follow_redirects=False)
check("invite link reopens same account", r.status_code == 302
      and r.headers["Location"] == "/")
check("still one invite account",
      len([k for k in A.users if k.startswith("invite-")]) == 1)

# email registration with a fresh code still works
check("admin re-login", login_admin())
r = c.post("/admin/codes", data={"n": 1, "label": "test2"}, follow_redirects=True)
codes2 = [k for k in A.codes.keys() if k != code]
check("admin creates second code", len(codes2) == 1)
code2 = codes2[0]
c.get("/admin/logout")
c.get("/logout")
r = c.post("/register", data={"email": "user@example.com", "password": "secret12", "code": code2}, follow_redirects=False)
check("register redirects", r.status_code == 302)
check("code2 marked used", A.codes[code2].get("used_by") == "user@example.com")

# code reuse rejected
c2 = A.app.test_client()
r = c2.post("/register", data={"email": "x@example.com", "password": "secret12", "code": code2})
check("code single-use", r.status_code == 400)

# register without code rejected
r = c2.post("/register", data={"email": "y@example.com", "password": "secret12", "code": ""})
check("code required", r.status_code == 400)

# login flow
c.get("/logout")
r = c.post("/login", data={"email": "user@example.com", "password": "secret12"}, follow_redirects=True)
check("login ok", r.status_code == 200 and b"Invoices" in r.data)

# business profile with Myanmar + Thai name
bdata = {"name": "ကုမ္ပဏီ Test บริษัท", "address": "Yangon, Myanmar",
         "email": "biz@example.com", "phone": "091234567",
         "website": "", "tax_id": "T123"}
r = c.post("/settings/business", data=bdata, follow_redirects=True)
check("business saved", r.status_code == 200 and "ကုမ္ပဏီ".encode("utf-8") in c.get("/settings/business").data)

# region: MMK + DD-MM-YYYY
c.post("/settings/region", data={"currency": "MMK", "date_format": "DD-MM-YYYY"}, follow_redirects=True)

# template color: green preset
c.post("/settings/template", data={"preset": "#059669"}, follow_redirects=True)
check("template color saved", A.invdata["user@example.com"]["business"]["accent_color"] == "#059669")

# add client
c.post("/clients", data={"name": "ConceptX School", "company": "ConceptX",
                         "email": "cx@example.com", "phone": "0999",
                         "address": "Mandalay"}, follow_redirects=True)
d = A.user_data("user@example.com")
check("client added", len(d["clients"]) == 1)
cid = d["clients"][0]["id"]

# add item
c.post("/items", data={"name": "Tuition", "description": "Monthly tuition สอนพิเศษ",
                       "rate": "150000"}, follow_redirects=True)
check("item added", len(d["items"]) == 1)

# create invoice with Myanmar/Thai lines
r = c.post("/docs/new", data={
    "type": "invoice", "client_id": cid,
    "issue_date": "2026-10-05", "due_date": "2026-10-12",
    "desc": ["သင်တန်းကြေး October", "ค่าธรรมเนียมพิเศษ"],
    "qty": ["2", "1"], "rate": ["500000", "260000"], "tax_pct": ["0", "5"],
    "discount_type": "percent", "discount_value": "10",
    "tax_type": "percent", "tax_value": "0", "shipping": "0",
    "notes": "ကျေးဇူးတင်ပါသည်", "terms": "Pay within 7 days"},
    follow_redirects=False)
check("invoice created", r.status_code == 302, str(r.status_code))
doc = d["documents"][-1]
check("number format INV0001 no dash", doc["number"] == "INV0001", doc["number"])
totals = A.doc_totals(doc)
# subtotal = 2*500000 + 1*260000 = 1260000; disc 10% = 126000; after=1134000
# line tax = 260000*5% = 13000; total = 1147000
check("totals math", abs(totals["total"] - 1147000) < 0.01, str(totals))

# PDF download + content check
r = c.get(f"/docs/{doc['id']}/pdf")
check("pdf 200", r.status_code == 200 and r.mimetype == "application/pdf", f"{r.status_code} {r.mimetype}")
_disp = r.headers.get("Content-Disposition") or ""
check("pdf served inline not attachment",
      "inline" in _disp and "attachment" not in _disp, _disp)
check("pdf inline keeps filename", "INV0001.pdf" in _disp, _disp)
pdf_bytes = r.data
check("pdf non-trivial", len(pdf_bytes) > 5000, str(len(pdf_bytes)))
open("/tmp/test-invoice.pdf", "wb").write(pdf_bytes)

# shared link: public page shows a View PDF button, PDF works logged-out
anon = A.app.test_client()
r = anon.get("/s/" + doc["share_token"])
check("public view 200", r.status_code == 200)
check("public view has pdf button", b"/pdf" in r.data and b"View PDF" in r.data)
r = anon.get("/s/" + doc["share_token"] + "/pdf")
check("public pdf 200 no login", r.status_code == 200 and r.mimetype == "application/pdf",
      f"{r.status_code} {r.mimetype}")
_pdisp = r.headers.get("Content-Disposition") or ""
check("public pdf served inline not attachment",
      "inline" in _pdisp and "attachment" not in _pdisp, _pdisp)
check("public pdf inline keeps filename", "INV0001.pdf" in _pdisp, _pdisp)
# byte equality is wrong here: fpdf2 stamps a per-render creation timestamp,
# so two renders of the same doc differ whenever they straddle a second.
# Compare extracted text instead — the document must be the same.
from pypdf import PdfReader as _PR
_pub_text = "\n".join(p.extract_text() or "" for p in _PR(io.BytesIO(r.data)).pages)
_own_text = "\n".join(p.extract_text() or "" for p in _PR(io.BytesIO(pdf_bytes)).pages)
check("public pdf same content", _pub_text == _own_text)

from pypdf import PdfReader
reader = PdfReader(io.BytesIO(pdf_bytes))
text = "\n".join(p.extract_text() or "" for p in reader.pages)
nospace = text.replace(" ", "").replace("\n", "")
check("pdf has business name (Myanmar)",
      "ကုမ္ပဏီ" in nospace,
      "pypdf inserts spaces in Myanmar runs; checked with spaces stripped")
check("pdf has Thai line", "ค่าธรรมเนียม" in text)
check("pdf has number", "INV0001" in text)
check("pdf has total", "1,147,000.00" in text, text[-200:])

# font coverage: every non-ASCII char in extracted text must exist in one of the fonts
from fontTools.ttLib import TTFont
fonts = [TTFont(f"fonts/{f}") for f in ("NotoSans-Regular.ttf", "NotoSans-Bold.ttf",
                                       "NotoSansThai-Regular.ttf", "Padauk-Regular.ttf")]
cmaps = [f.getBestCmap() for f in fonts]
missing = sorted({ch for ch in set(text) if ord(ch) > 127 and not any(ord(ch) in cm for cm in cmaps)})
check("font coverage (no tofu)", not missing, f"missing={missing[:10]}")

# accent color reflected in PDF: green #059669 = (5,150,105) -> fill "0.02 0.59 0.41 rg" approx
content = b"".join(p.get_contents().get_data() for p in reader.pages)
m = re.findall(rb"([\d.]+) ([\d.]+) ([\d.]+) rg", content)
def close(a, b): return abs(a - b) < 0.02
found_green = any(close(float(x), 5/255) and close(float(y), 150/255) and close(float(z), 105/255) for x, y, z in m)
check("template color in PDF", found_green, f"fills={m[:5]}")

# tabs filter: outstanding (due 2026-10-12 < today 2026-10-13 -> overdue)
r = c.get("/?tab=outstanding")
check("outstanding tab shows overdue invoice", b"INV0001" in r.data)
r = c.get("/?tab=paid")
check("paid tab empty", b"INV0001" not in r.data)
r = c.get("/")
check("list shows K currency + DD-MM-YYYY", b"K1,147,000.00" in r.data and b"12-10-2026" in r.data)

# english date format option
c.post("/settings/region", data={"currency": "MMK", "date_format": "DD Mon YYYY"}, follow_redirects=True)
r = c.get("/")
check("list shows English date", b"12 Oct 2026" in r.data)
reader = PdfReader(io.BytesIO(c.get(f"/docs/{doc['id']}/pdf").data))
etext = "\n".join(p.extract_text() or "" for p in reader.pages)
check("pdf has English date", "12 Oct 2026" in etext)
c.post("/settings/region", data={"currency": "MMK", "date_format": "Mon DD, YYYY"}, follow_redirects=True)
check("US English date", b"Oct 12, 2026" in c.get("/").data)
r = c.get("/settings/region")
check("region offers English formats", b"05 Oct 2026" in r.data and b"Oct 05, 2026" in r.data)

# one-time migration: legacy default becomes English, explicit choice sticks
A.invdata["user@example.com"]["business"].update({"date_format": "DD-MM-YYYY"})
A.invdata["user@example.com"]["business"].pop("_date_fmt_en", None)
c.get("/")
b = A.invdata["user@example.com"]["business"]
check("legacy default migrated", b["date_format"] == "DD Mon YYYY" and b.get("_date_fmt_en") is True)
c.post("/settings/region", data={"currency": "MMK", "date_format": "DD-MM-YYYY"}, follow_redirects=True)
c.get("/")
check("explicit DD-MM-YYYY sticks", A.invdata["user@example.com"]["business"]["date_format"] == "DD-MM-YYYY")

# mark paid
c.post(f"/docs/{doc['id']}/mark", data={"action": "paid"}, follow_redirects=True)
check("mark paid", A.eff_status(doc) == "paid")
r = c.get("/?tab=paid")
check("paid tab now shows", b"INV0001" in r.data)

# duplicate
r = c.post(f"/docs/{doc['id']}/duplicate", follow_redirects=False)
dup = d["documents"][-1]
check("duplicate new number", dup["number"] == "INV0002" and dup["id"] != doc["id"], dup["number"])

# estimate -> convert to invoice
r = c.post("/docs/new", data={"type": "estimate", "client_id": cid,
    "issue_date": "2026-10-13", "due_date": "",
    "desc": ["Quote item"], "qty": ["1"], "rate": ["100"], "tax_pct": ["0"],
    "discount_type": "amount", "discount_value": "0",
    "tax_type": "percent", "tax_value": "0", "shipping": "0",
    "notes": "", "terms": ""}, follow_redirects=False)
est = d["documents"][-1]
check("estimate EST0001", est["number"] == "EST0001", est["number"])
r = c.post(f"/docs/{est['id']}/convert", follow_redirects=False)
inv3 = d["documents"][-1]
check("convert -> INV0003", inv3["type"] == "invoice" and inv3["number"] == "INV0003", inv3["number"])
check("estimate accepted", est["status"] == "accepted")

# estimates tab
r = c.get("/estimates?tab=accepted")
check("estimates accepted tab", b"EST0001" in r.data)

# receipt via FAB sheet link
r = c.post("/docs/new", data={"type": "receipt", "client_id": cid,
    "issue_date": "2026-10-13", "due_date": "",
    "desc": ["Cash received"], "qty": ["1"], "rate": ["50000"], "tax_pct": ["0"],
    "discount_type": "amount", "discount_value": "0",
    "tax_type": "percent", "tax_value": "0", "shipping": "0",
    "notes": "", "terms": ""}, follow_redirects=False)
rec = d["documents"][-1]
check("receipt REC0001 paid", rec["number"] == "REC0001" and rec["status"] == "paid", rec["number"])
r = c.get("/receipts")
check("receipts list", b"REC0001" in r.data)

# expenses
c.post("/expenses", data={"date": "2026-10-10", "category": "Transport",
                          "vendor": "Taxi", "amount": "15000", "note": "client visit"},
       follow_redirects=True)
check("expense added", len(d["expenses"]) == 1)
r = c.get("/expenses")
check("expenses page shows", b"Taxi" in r.data and b"K15,000.00" in r.data)

# share link without login
token = doc["share_token"]
anon = A.app.test_client()
r = anon.get("/s/" + token)
check("public share no login", r.status_code == 200 and b"INV0001" in r.data)
check("bad token 404", anon.get("/s/badtoken").status_code == 404)

# CSV exports
r = c.get("/settings/export/invoices.csv")
check("invoice csv", r.status_code == 200 and b"INV0001" in r.data and b"1147000.00" in r.data)
r = c.get("/settings/export/expenses.csv")
check("expense csv", r.status_code == 200 and b"Taxi" in r.data)

# backup
import json as J
r = c.get("/settings/backup")
blob = J.loads(r.data)
check("backup json", blob["data"]["business"]["name"].startswith("ကုမ္ပဏီ") and len(blob["data"]["documents"]) >= 4)

# reports
r = c.get("/reports")
check("reports page", r.status_code == 200 and b"2026-10" in r.data and b"Outstanding" in r.data)

# recurring: schedule monthly from invoice template, next_date in past -> generates on next page load
c.post("/recurring", data={"doc_id": doc["id"], "start_date": "2026-09-01"}, follow_redirects=True)
n_before = len(d["documents"])
c.get("/")  # triggers _run_recurring
n_after = len(d["documents"])
check("recurring generated", n_after > n_before, f"{n_before}->{n_after}")
gen = d["documents"][-1]
check("recurring draft copy", gen["status"] == "draft" and gen["number"].startswith("INV"), gen["number"])

# numbering settings: change prefix + next number
c.post("/settings/numbering", data={"inv_prefix": "BILL", "next_invoice": "50",
                                    "est_prefix": "EST", "next_estimate": "1",
                                    "rec_prefix": "REC", "next_receipt": "1"},
       follow_redirects=True)
r = c.post("/docs/new", data={"type": "invoice", "client_id": cid,
    "issue_date": "2026-10-13", "due_date": "",
    "desc": ["x"], "qty": ["1"], "rate": ["1"], "tax_pct": ["0"],
    "discount_type": "amount", "discount_value": "0",
    "tax_type": "percent", "tax_value": "0", "shipping": "0",
    "notes": "", "terms": ""}, follow_redirects=False)
newdoc = d["documents"][-1]
check("custom prefix+next", newdoc["number"] == "BILL0050", newdoc["number"])

# --- per-document signature switch + native Share button ---
import base64
from PIL import Image, ImageDraw

# editor shows the checkbox, checked by default, with a hint (no signature yet)
r = c.get("/docs/new?type=invoice")
check("editor has signature checkbox",
      b'Include signature on the PDF' in r.data and b'name="show_signature"' in r.data)
check("editor checkbox checked by default",
      re.search(rb'name="show_signature"[^>]*checked', r.data) is not None)
check("editor hints at missing signature",
      b"No signature saved yet" in r.data and b"/settings/signature" in r.data)

# save a signature via the settings form (small black-on-white PNG)
buf = io.BytesIO()
_im = Image.new("RGB", (200, 80), "white")
_dr = ImageDraw.Draw(_im)
_dr.line([(10, 50), (60, 20), (120, 60), (190, 30)], fill="black", width=3)
_im.save(buf, "PNG")
sig_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
r = c.post("/settings/signature", data={"signature_data": sig_url}, follow_redirects=True)
sig_path = A.invdata["user@example.com"]["business"].get("signature_path") or ""
check("signature saved", bool(sig_path) and os.path.isfile(os.path.join(tmpd, sig_path)), sig_path)
r = c.get("/docs/new?type=invoice")
check("editor hint gone once signature saved", b"No signature saved yet" not in r.data)

def _pdf_text(doc_id):
    rr = c.get(f"/docs/{doc_id}/pdf")
    assert rr.status_code == 200, rr.status_code
    rd = PdfReader(io.BytesIO(rr.data))
    return "\n".join(p.extract_text() or "" for p in rd.pages)

_sigform = {"type": "invoice", "client_id": cid,
            "issue_date": "2026-10-13", "due_date": "",
            "desc": ["Sig test"], "qty": ["1"], "rate": ["1000"], "tax_pct": ["0"],
            "discount_type": "amount", "discount_value": "0",
            "tax_type": "percent", "tax_value": "0", "shipping": "0",
            "notes": "", "terms": ""}

# new invoice with the box checked -> flag True, PDF carries the signature
r = c.post("/docs/new", data=dict(_sigform, show_signature="on"), follow_redirects=False)
sigdoc = d["documents"][-1]
check("new doc show_signature True", sigdoc.get("show_signature") is True)
check("pdf includes signature when on", "Authorized signature" in _pdf_text(sigdoc["id"]))

# same doc edited with the box unchecked -> flag False, PDF drops the signature
r = c.post(f"/docs/{sigdoc['id']}/edit", data=dict(_sigform), follow_redirects=False)
check("edit unchecks signature", sigdoc.get("show_signature") is False)
check("pdf omits signature when off", "Authorized signature" not in _pdf_text(sigdoc["id"]))

# new invoice without the checkbox -> False (unchecked boxes post nothing)
r = c.post("/docs/new", data=dict(_sigform), follow_redirects=False)
offdoc = d["documents"][-1]
check("new doc without checkbox is False", offdoc.get("show_signature") is False)

# legacy document without the key behaves as True (signature shows)
doc.pop("show_signature", None)
check("legacy doc without flag shows signature",
      "Authorized signature" in _pdf_text(doc["id"]))

# detail page: native Share button + existing share options intact
r = c.get(f"/docs/{sigdoc['id']}")
check("detail has native Share button",
      b'id="sharebtn"' in r.data and b"navigator.share" in r.data)
check("detail share carries public url",
      sigdoc["share_token"].encode() in r.data)
check("detail share title is Invoice + number",
      ("Invoice " + sigdoc["number"]).encode() in r.data)
check("detail keeps copy/whatsapp/email share",
      b"Copy link" in r.data and b"Share on WhatsApp" in r.data and b"Share by email" in r.data)
check("detail button is View PDF now",
      b"View PDF" in r.data and b"Download PDF" not in r.data)

# --- public share page: Share + Back buttons, no dead end ---
r = anon.get("/s/" + token)
check("public has Share button",
      b'id="sharepdfbtn"' in r.data and b"navigator.share" in r.data)
check("public share fetches pdf as file",
      b"canShare" in r.data and b"/pdf" in r.data and b"new File" in r.data)
check("public has Back button",
      b"history.back()" in r.data and "← Back".encode() in r.data)
check("public button is View PDF now",
      b"View PDF" in r.data and b"Download PDF" not in r.data and b"/pdf" in r.data)
check("public has share tip",
      b"tap Share to send this invoice without downloading it" in r.data)

# --- payment methods: saved once, printed on every invoice ---
pay_text = "KBZPay: 09 xxx xxx xxx\nWavePay: 09 xxx xxx xxx"
r = c.post("/settings/payments", data={"payment_details": pay_text}, follow_redirects=True)
check("payments saved",
      A.invdata["user@example.com"]["business"]["payment_details"] == pay_text)
check("payments shown on settings page", b"KBZPay: 09 xxx xxx xxx" in r.data)
import json as _J
_on_disk = _J.load(open(os.path.join(tmpd, "invdata.json")))
check("payments persisted to disk",
      _on_disk["user@example.com"]["business"]["payment_details"] == pay_text)

# rendered PDF: payment text under "Payment details", before Notes, notes untouched
ptxt = _pdf_text(doc["id"])
# pypdf extracts some Myanmar sequences with control chars (fpdf2 ligature
# glyphs map to \x02/\x03/\x07), so strip those before matching; the tail of
# the notes ("တင်ပါသည်") extracts cleanly and is unique to the notes.
ptxt_ns = re.sub(r"[\x00-\x1f]", "", ptxt.replace(" ", "").replace("\n", ""))
check("pdf has Payment details heading", "Payment details" in ptxt)
check("pdf has saved payment text", "KBZPay: 09 xxx xxx xxx" in ptxt)
check("pdf payment block before notes",
      ptxt.index("Payment details") < ptxt.index("Notes"))
check("pdf notes untouched", "တင်ပါသည်" in ptxt_ns)

# editor: no hint while payment methods are set, hint + link when empty
r = c.get("/docs/new?type=invoice")
check("editor hides payment hint when set", b"Payment methods not set" not in r.data)
c.post("/settings/payments", data={"payment_details": ""}, follow_redirects=True)
check("payments cleared", A.invdata["user@example.com"]["business"]["payment_details"] == "")
r = c.get("/docs/new?type=invoice")
check("editor shows payment hint when empty",
      b"Payment methods not set" in r.data and b"/settings/payments" in r.data)

# detail page: edit-payment-methods link + file-share Share button
r = c.get(f"/docs/{doc['id']}")
check("detail has edit payment methods link",
      b"Edit payment methods" in r.data and b"/settings/payments" in r.data)
check("detail share tries pdf file first",
      b"canShare" in r.data and b"new File" in r.data)

# --- Zoom price table: computed prices, previous vs current rate, screenshot ---
_zdb = A.default_business()
check("zoom defaults",
      _zdb["zoom_rate_ks_per_usd"] == 5600
      and _zdb["zoom_prev_rate_ks_per_usd"] == 4400
      and abs(_zdb["zoom_usd_per_month"] - 35000 / 4400) < 1e-9
      and _zdb["zoom_official_1mo_usd"] == 16.99
      and _zdb["zoom_official_3mo_usd"] == 50.97
      and "zoom_3mo_ks" not in _zdb and "zoom_1mo_ks" not in _zdb)

r = c.get("/settings/business")
check("settings shows zoom fields",
      b"zoom_rate_ks_per_usd" in r.data and b"zoom_prev_rate_ks_per_usd" in r.data
      and b"zoom_usd_per_month" in r.data)

_zoomform = dict(bdata, zoom_rate_ks_per_usd="5600", zoom_prev_rate_ks_per_usd="4400",
                 zoom_usd_per_month="7.9545", zoom_official_1mo_usd="16.99",
                 zoom_official_3mo_usd="50.97")
r = c.post("/settings/business", data=_zoomform, follow_redirects=True)
_biz = A.invdata["user@example.com"]["business"]
check("zoom settings saved",
      _biz["zoom_rate_ks_per_usd"] == 5600 and _biz["zoom_prev_rate_ks_per_usd"] == 4400
      and abs(_biz["zoom_usd_per_month"] - 35000 / 4400) < 1e-9
      and _biz["zoom_official_1mo_usd"] == 16.99 and _biz["zoom_official_3mo_usd"] == 50.97)
r = c.get("/settings/business")
check("settings shows usd base as 7.9545", b"7.9545" in r.data)

_zp = A.zoom_prices(_biz)
check("computed prices at defaults",
      _zp["ks_1mo"] == 44545 and _zp["ks_3mo"] == 133636
      and _zp["prev_ks_1mo"] == 35000 and _zp["prev_ks_3mo"] == 105000
      and _zp["off_1mo_ks"] == 95144 and _zp["off_3mo_ks"] == 285432,
      str(_zp))

r = c.get("/docs/new?type=invoice")
check("editor has zoom checkbox + preset + proof upload",
      b'name="show_zoom_prices"' in r.data and b"Show Zoom price table" in r.data
      and b"Add Zoom Pro (100 participants)" in r.data and b'id="addzoom"' in r.data
      and b'name="proof_image"' in r.data)
check("editor form is multipart", b"multipart/form-data" in r.data)
check("editor preset uses computed 3-month price", b"133636" in r.data)
check("editor hint shows current prices",
      b"K44,545" in r.data and b"K133,636" in r.data)

_zform = {"type": "invoice", "client_id": cid,
          "issue_date": "2026-10-13", "due_date": "",
          "desc": ["Zoom Pro License - 100 participants, 3 months"], "qty": ["1"],
          "rate": ["133636"], "tax_pct": ["0"],
          "discount_type": "amount", "discount_value": "0",
          "tax_type": "percent", "tax_value": "0", "shipping": "0",
          "notes": "", "terms": "", "show_zoom_prices": "on"}
r = c.post("/docs/new", data=_zform, follow_redirects=False)
zdoc = d["documents"][-1]
check("zoom invoice has flag", zdoc.get("show_zoom_prices") is True)
_ztxt = _pdf_text(zdoc["id"])
for _s in ("Zoom Pro - 100 participants",
           "Previous rate: 1 USD = 4,400 Ks", "Current rate: 1 USD = 5,600 Ks",
           "$7.95 x 4,400 Ks = K35,000", "$23.86 x 4,400 Ks = K105,000",
           "$7.95 x 5,600 Ks = K44,545", "$23.86 x 5,600 Ks = K133,636",
           "$16.99 (K95,144)", "$50.97 (K285,432)"):
    check("pdf zoom table: " + _s, _s in _ztxt)
_zpdf = c.get(f"/docs/{zdoc['id']}/pdf").data
_zreader = PdfReader(io.BytesIO(_zpdf))
_zimgs = [im.image for p in _zreader.pages for im in p.images]
check("pdf embeds default proof screenshot",
      any(im.size == (1139, 1062) for im in _zimgs),
      str([im.size for im in _zimgs]))

_plain = dict(_zform)
_plain.pop("show_zoom_prices")
r = c.post("/docs/new", data=_plain, follow_redirects=False)
plaindoc = d["documents"][-1]
check("plain invoice has no zoom flag", not plaindoc.get("show_zoom_prices"))
check("plain pdf has no zoom table",
      "Zoom Pro - 100 participants" not in _pdf_text(plaindoc["id"]))
_ppdf = c.get(f"/docs/{plaindoc['id']}/pdf").data
_pimgs = [im for p in PdfReader(io.BytesIO(_ppdf)).pages for im in p.images]
check("plain pdf embeds no images", len(_pimgs) == 0, str(len(_pimgs)))

# changing the current rate recomputes both prices (4400 -> 35000 / 105000)
c.post("/settings/business", data=dict(_zoomform, zoom_rate_ks_per_usd="4400"),
       follow_redirects=True)
_zp2 = A.zoom_prices(A.invdata["user@example.com"]["business"])
check("rate change recomputes both prices",
      _zp2["ks_1mo"] == 35000 and _zp2["ks_3mo"] == 105000, str(_zp2))
r = c.post("/docs/new", data=_zform, follow_redirects=False)
_rtxt = _pdf_text(d["documents"][-1]["id"])
check("pdf at rate 4400 shows recomputed prices",
      "Current rate: 1 USD = 4,400 Ks" in _rtxt
      and "$7.95 x 4,400 Ks = K35,000" in _rtxt
      and "$23.86 x 4,400 Ks = K105,000" in _rtxt, _rtxt[-400:])
c.post("/settings/business", data=_zoomform, follow_redirects=True)

# changing the previous rate recomputes the previous prices only
c.post("/settings/business", data=dict(_zoomform, zoom_prev_rate_ks_per_usd="5000"),
       follow_redirects=True)
_zp3 = A.zoom_prices(A.invdata["user@example.com"]["business"])
check("previous rate change recomputes previous prices",
      _zp3["prev_ks_1mo"] == 39773 and _zp3["prev_ks_3mo"] == 119318
      and _zp3["ks_1mo"] == 44545 and _zp3["ks_3mo"] == 133636, str(_zp3))
c.post("/settings/business", data=_zoomform, follow_redirects=True)

# per-invoice screenshot replaces the default in the PDF
_buf = io.BytesIO()
Image.new("RGB", (100, 50), "red").save(_buf, "PNG")
_buf.seek(0)
r = c.post("/docs/new", data=dict(_zform, proof_image=(_buf, "proof.png")),
           follow_redirects=False)
udoc = d["documents"][-1]
check("per-invoice proof stored",
      bool(udoc.get("proof_image"))
      and os.path.isfile(os.path.join(tmpd, udoc["proof_image"])),
      udoc.get("proof_image") or "")
_updf = c.get(f"/docs/{udoc['id']}/pdf").data
_uimgs = [im.image for p in PdfReader(io.BytesIO(_updf)).pages for im in p.images]
check("uploaded proof overrides default in pdf",
      any(im.size == (100, 50) for im in _uimgs)
      and not any(im.size == (1139, 1062) for im in _uimgs),
      str([im.size for im in _uimgs]))

# admin: revoke code + delete user
c.get("/logout")
login_admin()
c.post("/admin/codes", data={"n": 1, "label": "torevoke"}, follow_redirects=True)
rc = [k for k in A.codes if A.codes[k].get("label") == "torevoke"][0]
c.post(f"/admin/revoke/{rc}", follow_redirects=True)
check("revoke code", rc not in A.codes)
c.post("/admin/users/delete", data={"email": "user@example.com"}, follow_redirects=True)
check("delete user", "user@example.com" not in A.users and "user@example.com" not in A.invdata)

print(f"\n{len(passed)} passed, {len(failed)} failed")
if failed:
    print("FAILED:", failed)
    sys.exit(1)
shutil.rmtree(tmpd, ignore_errors=True)
