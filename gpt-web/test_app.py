"""Tests for the Chat GPT web app via Flask test client.

Covers Excel (.xlsx) uploads to /api/upload_chat: a real .xlsx reaches
the model as document text and is stored in the conversation, a corrupt
.xlsx fails cleanly, and old .xls stays rejected. GPT is stubbed — no
real API call happens.
Run: python3 test_app.py
"""
import io, json, os, shutil, sys, tempfile

tmpd = tempfile.mkdtemp(prefix="gpttest_")
os.environ["DATA_DIR"] = tmpd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as A
import brain

A.app.config["TESTING"] = True
passed, failed = [], []

def check(name, cond, extra=""):
    (passed if cond else failed).append(name)
    print(("PASS " if cond else "FAIL ") + name + (" — " + extra if extra and not cond else ""))

# Stub GPT so no real API call happens; record what reaches the model.
seen_attachments = []
def fake_ask(messages, max_tokens=None, attachments=None, project_context=None):
    seen_attachments.append(attachments)
    return ("Hello back!", {"input_tokens": 5, "output_tokens": 5})
brain.ask_gpt = fake_ask

def redeem(code):
    c = A.app.test_client()
    r = c.post("/api/redeem", json={"code": code})
    assert r.status_code == 200 and r.json.get("ok"), r.json
    return c

# Fresh invite code for the test user.
CODE = "TESTCODE1"
A.codes[CODE] = {"used_by": None, "label": "test",
                 "created": "2026-11-19", "used_at": None}

def make_xlsx_bytes():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(["Product", "Qty", "Price"])
    ws.append(["Apple", 10, 2.5])
    ws2 = wb.create_sheet("Notes")
    ws2.append(["Hello world"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

# 1. Logged out -> 401.
c0 = A.app.test_client()
r = c0.post("/api/upload_chat",
            data={"message": "x",
                  "file": (io.BytesIO(make_xlsx_bytes()), "sales.xlsx")},
            content_type="multipart/form-data")
check("upload 401 when logged out", r.status_code == 401, f"got {r.status_code}")

c = redeem(CODE)

# 2. A real .xlsx reaches the model as document text.
r = c.post("/api/upload_chat",
           data={"message": "What is in this sheet?",
                 "file": (io.BytesIO(make_xlsx_bytes()), "sales.xlsx")},
           content_type="multipart/form-data")
check("xlsx upload returns 200",
      r.status_code == 200 and r.json.get("ok"), f"got {r.status_code} {r.json}")
doc_texts = [a.get("text", "") for a in (seen_attachments[-1] or [])
             if a.get("kind") == "doc"]
check("xlsx text reaches the model",
      doc_texts and "Apple" in doc_texts[0] and "Sales" in doc_texts[0]
      and "10" in doc_texts[0] and "2.5" in doc_texts[0],
      f"got {doc_texts}")

# 3. The stored conversation keeps the sheet text for follow-ups.
r = c.get("/api/convos")
active = (r.json or {}).get("active")
r = c.post("/api/convos/open", json={"id": active})
msgs = (r.json or {}).get("messages", [])
contexts = [m.get("context", "") for m in msgs]
check("xlsx text stored in conversation context",
      any("Apple" in ctx and "Sales" in ctx for ctx in contexts),
      f"got {r.json}")

# 4. Corrupt .xlsx -> clean 400, not a 500.
r = c.post("/api/upload_chat",
           data={"message": "x",
                 "file": (io.BytesIO(b"this is not a zip file"), "bad.xlsx")},
           content_type="multipart/form-data")
check("corrupt xlsx rejected with a clean error",
      r.status_code == 400 and "Couldn't read" in (r.json or {}).get("error", ""),
      f"got {r.status_code} {r.json}")

# 5. Old .xls stays rejected.
r = c.post("/api/upload_chat",
           data={"message": "x",
                 "file": (io.BytesIO(b"not a real xls"), "old.xls")},
           content_type="multipart/form-data")
check("xls still rejected",
      r.status_code == 400 and "isn't supported" in (r.json or {}).get("error", ""),
      f"got {r.status_code} {r.json}")

print(f"\n{len(passed)} passed, {len(failed)} failed")
if failed:
    print("FAILED:", failed)
    sys.exit(1)
shutil.rmtree(tmpd, ignore_errors=True)
