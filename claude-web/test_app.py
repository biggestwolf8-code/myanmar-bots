"""Tests for the Claude Coworker web app via Flask test client.

Covers the chat-history endpoint (/api/history): it must need a login,
return the saved messages after a chat exchange, and return an empty
list for a fresh code. Claude is stubbed — no real API call happens.
Run: python3 test_app.py
"""
import io, json, os, shutil, sys, tempfile

tmpd = tempfile.mkdtemp(prefix="claudetest_")
os.environ["DATA_DIR"] = tmpd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as A
import brain

A.app.config["TESTING"] = True
passed, failed = [], []

def check(name, cond, extra=""):
    (passed if cond else failed).append(name)
    print(("PASS " if cond else "FAIL ") + name + (" — " + extra if extra and not cond else ""))

# Stub Claude so no real API call happens; record what reaches the model.
seen_attachments = []
def fake_ask(messages, max_tokens=None, attachments=None):
    seen_attachments.append(attachments)
    return ("Hello back!", {"input_tokens": 5, "output_tokens": 5})
brain.ask_claude = fake_ask

def redeem(code):
    c = A.app.test_client()
    r = c.post("/api/redeem", json={"code": code})
    assert r.status_code == 200 and r.json.get("ok"), r.json
    return c

# Fresh invite code for the test user.
CODE = "TESTCODE1"
A.codes[CODE] = {"used_by": None, "label": "test",
                 "created": "2026-11-19", "used_at": None}

# 1. Logged out -> 401, same as the other /api routes.
c0 = A.app.test_client()
r = c0.get("/api/history")
check("history 401 when logged out", r.status_code == 401, f"got {r.status_code}")

# 2. Fresh code -> empty list.
c = redeem(CODE)
r = c.get("/api/history")
check("history empty for fresh code",
      r.status_code == 200 and r.json == {"ok": True, "history": []},
      f"got {r.json}")

# 3. After a chat exchange -> both messages come back.
r = c.post("/api/chat", json={"message": "Hello there"})
check("chat exchange ok", r.status_code == 200 and r.json.get("ok"),
      f"got {r.status_code} {r.json}")
r = c.get("/api/history")
check("history returns saved messages after chat",
      r.status_code == 200 and r.json == {
          "ok": True,
          "history": [{"role": "user", "content": "Hello there"},
                      {"role": "assistant", "content": "Hello back!"}]},
      f"got {r.json}")

# 4. The exchange is on disk (webhistories.json), so a restart/reload
#    would load the same chat back.
with open(os.path.join(tmpd, "webhistories.json"), encoding="utf-8") as f:
    saved = json.load(f)
check("history persisted to webhistories.json",
      saved.get(CODE) == [{"role": "user", "content": "Hello there"},
                          {"role": "assistant", "content": "Hello back!"}],
      f"got {saved}")

# 5. Agent-style entries (API block lists / tool turns) must not break
#    the endpoint: text blocks are joined, tool entries are skipped.
A.histories[CODE] = [
    {"role": "user", "content": [{"type": "text", "text": "Agent task"}]},
    {"role": "assistant", "content": [
        {"type": "text", "text": "Done."},
        {"type": "tool_use", "id": "x", "name": "run_python", "input": {}}]},
    {"role": "tool", "content": "result"},
]
r = c.get("/api/history")
check("history skips tool entries, joins text blocks",
      r.status_code == 200 and r.json == {
          "ok": True,
          "history": [{"role": "user", "content": "Agent task"},
                      {"role": "assistant", "content": "Done."}]},
      f"got {r.json}")

# 6. "+ New chat" wipes the stored history (existing behaviour, guarded).
r = c.post("/api/new")
check("new chat ok", r.status_code == 200 and r.json.get("ok"), f"got {r.json}")
r = c.get("/api/history")
check("new chat clears history",
      r.status_code == 200 and r.json == {"ok": True, "history": []},
      f"got {r.json}")

# 7. Excel (.xlsx) upload: a real file reaches the model and is stored
#    in history for follow-ups.
def make_xlsx_bytes():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(["Product", "Qty", "Price"])
    ws.append(["Apple", 10, 2.5])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

# 7a. Logged out -> 401.
r = c0.post("/api/upload_chat",
            data={"message": "x",
                  "file": (io.BytesIO(make_xlsx_bytes()), "sales.xlsx")},
            content_type="multipart/form-data")
check("xlsx upload 401 when logged out", r.status_code == 401, f"got {r.status_code}")

# 7b. A real .xlsx reaches the model as document text.
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

# 7c. The stored history keeps the sheet text for follow-ups.
r = c.get("/api/history")
hist_texts = [m.get("content", "") for m in (r.json or {}).get("history", [])]
check("xlsx text stored in history",
      any("Apple" in t and "Sales" in t for t in hist_texts),
      f"got {r.json}")

# 7d. Corrupt .xlsx -> clean 400, not a 500.
r = c.post("/api/upload_chat",
           data={"message": "x",
                 "file": (io.BytesIO(b"this is not a zip file"), "bad.xlsx")},
           content_type="multipart/form-data")
check("corrupt xlsx rejected with a clean error",
      r.status_code == 400 and "Couldn't read" in (r.json or {}).get("error", ""),
      f"got {r.status_code} {r.json}")

# 7e. Old .xls stays rejected.
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
