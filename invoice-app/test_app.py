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

# register with code
r = c.get("/i/" + code)
check("invite link prefills", r.status_code == 200 and code.encode() in r.data)
r = c.post("/register", data={"email": "user@example.com", "password": "secret12", "code": code}, follow_redirects=False)
check("register redirects", r.status_code == 302)
check("code marked used", A.codes[code].get("used_by") == "user@example.com")

# code reuse rejected
c2 = A.app.test_client()
r = c2.post("/register", data={"email": "x@example.com", "password": "secret12", "code": code})
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
pdf_bytes = r.data
check("pdf non-trivial", len(pdf_bytes) > 5000, str(len(pdf_bytes)))
open("/tmp/test-invoice.pdf", "wb").write(pdf_bytes)

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
