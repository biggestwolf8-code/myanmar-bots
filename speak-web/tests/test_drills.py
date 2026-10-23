"""Mock-based tests for the Practice Drills feature (upgrade + variations).

The sandbox has no OpenAI key, so all brain.* network functions are mocked.
Run:  python3 -m unittest discover -s tests -v   (from speak-web/)
"""
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

TMPDIR = tempfile.mkdtemp(prefix="speak-drill-test-")
os.environ["DATA_DIR"] = TMPDIR
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod  # noqa: E402
import brain  # noqa: E402

LESSON_ID = "meeting-new-people"
UPGRADE_ITEMS = [
    {"boring_en": f"Boring phrase {i}.", "boring_my": f"ပျင်းစရာ {i}။"}
    for i in range(1, 6)
]
VARIATION_ITEMS = [
    {"base_en": f"Base {i}.", "base_my": f"အခြေခံ {i}။",
     "section": "phrases",
     "variants": [{"en": f"Variant {i}-{k}.", "my": f"ကွဲ {i}-{k}။"}
                  for k in range(1, 4)]}
    for i in range(1, 6)
]
USAGE = {"input_tokens": 100, "output_tokens": 50, "cost": 0.001}


def make_upgrade_fb(score=5):
    return {"said": "My brilliant version here.",
            "score": score,
            "flow_en": "Much livelier!", "flow_my": "ပိုကောင်းတယ်!",
            "brilliant_en": "A truly brilliant line.",
            "brilliant_my": "အံ့သြစရာစာကြောင်း။",
            "tip_en": "Add one specific detail. Keep going!",
            "tip_my": "အသေးစိတ်တစ်ခုထည့်ပါ။"}, USAGE


def make_expr_fb(score=3):
    return {"said": "I said a variant.",
            "score": score,
            "alternatives": [{"instead_of": "", "try_this": "Even better way.",
                              "try_this_my": "ပိုကောင်းတဲ့နည်း။"}],
            "flow_en": "Good flow.", "flow_my": "ကောင်းတယ်။",
            "tip_en": "Speak with confidence. Keep going!",
            "tip_my": "ယုံကြည်မှုနဲ့ပြောပါ။"}, USAGE


class DrillTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        brain.OPENAI_API_KEY = "test-key"  # satisfy _guard_voice
        cls.client = appmod.app.test_client()
        cls.code = "TESTDRIL"
        cls.sid = "sid-test-drill-001"
        con = sqlite3.connect(os.path.join(TMPDIR, "speak.db"))
        con.execute("INSERT INTO codes(code, created, label) VALUES(?,?,?)",
                    (cls.code, "2026-10-23T00:00:00", "test"))
        con.execute("INSERT INTO sessions(sid, code, created) VALUES(?,?,?)",
                    (cls.sid, cls.code, "2026-10-23T00:00:00"))
        con.commit()
        con.close()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMPDIR, ignore_errors=True)

    def login(self):
        c = appmod.app.test_client()
        with c.session_transaction() as s:
            s["sid"] = self.sid
        return c

    def audio_form(self, **extra):
        data = {"audio": (io.BytesIO(b"\x00" * 4000), "drill.webm"),
                "lesson_id": LESSON_ID}
        data.update(extra)
        return data

    # ------------------------------------------------------------ page ---
    def test_drill_page_requires_login(self):
        r = self.client.get(f"/drill/{LESSON_ID}")
        self.assertEqual(r.status_code, 302)

    def test_drill_page_renders(self):
        c = self.login()
        r = c.get(f"/drill/{LESSON_ID}")
        self.assertEqual(r.status_code, 200)
        html = r.data.decode()
        self.assertIn("Practice drills", html)
        self.assertIn("Boring → Brilliant", html)
        self.assertIn("Fresh Variations", html)

    def test_drill_page_bad_lesson(self):
        c = self.login()
        r = c.get("/drill/no-such-lesson")
        self.assertEqual(r.status_code, 404)

    def test_lesson_page_has_drill_links(self):
        c = self.login()
        r = c.get(f"/lesson/{LESSON_ID}")
        self.assertEqual(r.status_code, 200)
        html = r.data.decode()
        self.assertIn(f"/drill/{LESSON_ID}?mode=upgrade", html)
        self.assertIn(f"/drill/{LESSON_ID}?mode=variations", html)

    # ------------------------------------------------------------ start ---
    def test_start_requires_login(self):
        r = self.client.post("/api/drill/start",
                             json={"lesson_id": LESSON_ID, "mode": "upgrade"})
        self.assertEqual(r.status_code, 401)

    @patch.object(brain, "drill_items", return_value=(UPGRADE_ITEMS, USAGE))
    def test_start_upgrade(self, _mock):
        c = self.login()
        r = c.post("/api/drill/start",
                   json={"lesson_id": LESSON_ID, "mode": "upgrade"})
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertTrue(j["ok"])
        self.assertEqual(j["mode"], "upgrade")
        self.assertEqual(len(j["items"]), 5)
        for it in j["items"]:
            self.assertIn("boring_en", it)
            self.assertIn("boring_my", it)

    @patch.object(brain, "drill_items", return_value=(VARIATION_ITEMS, USAGE))
    def test_start_variations(self, _mock):
        c = self.login()
        r = c.post("/api/drill/start",
                   json={"lesson_id": LESSON_ID, "mode": "variations"})
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertTrue(j["ok"])
        self.assertEqual(j["mode"], "variations")
        self.assertEqual(len(j["items"]), 5)
        for it in j["items"]:
            self.assertIn("base_en", it)
            self.assertIn("variants", it)
            self.assertEqual(len(it["variants"]), 3)
            for v in it["variants"]:
                self.assertIn("en", v)
                self.assertIn("my", v)

    @patch.object(brain, "drill_items", return_value=(UPGRADE_ITEMS, USAGE))
    def test_start_bad_mode_and_lesson(self, _mock):
        c = self.login()
        r = c.post("/api/drill/start",
                   json={"lesson_id": LESSON_ID, "mode": "nope"})
        self.assertEqual(r.status_code, 400)
        r = c.post("/api/drill/start",
                   json={"lesson_id": "no-such-lesson", "mode": "upgrade"})
        self.assertEqual(r.status_code, 400)

    # ------------------------------------------------------------ turn ---
    def test_turn_requires_login(self):
        r = self.client.post("/api/drill/turn",
                             data=self.audio_form(mode="upgrade", item="{}"),
                             content_type="multipart/form-data")
        self.assertEqual(r.status_code, 401)

    @patch.object(brain, "transcribe", return_value="My brilliant upgrade!")
    @patch.object(brain, "upgrade_feedback",
                  return_value=make_upgrade_fb(score=5))
    def test_turn_upgrade(self, _mfb, _mtr):
        c = self.login()
        item = json.dumps({"boring_en": "Boring phrase 1.",
                           "boring_my": "ပျင်းစရာ ၁။"})
        r = c.post("/api/drill/turn",
                   data=self.audio_form(mode="upgrade", item=item),
                   content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertTrue(j["ok"])
        self.assertEqual(j["score"], 5)
        self.assertEqual(j["said"], "My brilliant version here.")
        self.assertIn("brilliant_en", j)
        self.assertIn("brilliant_my", j)
        self.assertIn("flow_my", j)
        self.assertIn("tip_my", j)
        self.assertEqual(j["xp"], 10)          # score>=3 -> 10 XP
        self.assertEqual(j["total_xp"], 10)
        self.assertEqual(j["streak"], 1)

    @patch.object(brain, "transcribe", return_value="I said a variant.")
    @patch.object(brain, "expression_feedback",
                  return_value=make_expr_fb(score=2))
    def test_turn_variations_low_score(self, _mfb, _mtr):
        c = self.login()
        item = json.dumps({"base_en": "Base 1.", "base_my": "အခြေခံ ၁။",
                           "section": "phrases",
                           "variant_en": "Variant 1-1.",
                           "variant_my": "ကွဲ ၁-၁။"})
        r = c.post("/api/drill/turn",
                   data=self.audio_form(mode="variations", item=item),
                   content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertTrue(j["ok"])
        self.assertEqual(j["score"], 2)
        self.assertIn("alternatives", j)
        self.assertEqual(len(j["alternatives"]), 1)
        self.assertNotIn("brilliant_en", j)   # variations has no brilliant key
        self.assertEqual(j["xp"], 2)          # score<3 -> 2 XP
        # XP accumulates on the same code (10 from previous test)
        self.assertEqual(j["total_xp"], 12)

    @patch.object(brain, "transcribe", return_value="")
    def test_turn_empty_audio(self, _mtr):
        c = self.login()
        item = json.dumps({"boring_en": "Boring.", "boring_my": "ပျင်းစရာ။"})
        r = c.post("/api/drill/turn",
                   data=self.audio_form(mode="upgrade", item=item),
                   content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertTrue(j["ok"])
        self.assertEqual(j["score"], 1)
        self.assertEqual(j["xp"], 0)

    def test_turn_daily_limit(self):
        c = self.login()
        con = sqlite3.connect(os.path.join(TMPDIR, "speak.db"))
        con.execute("UPDATE codes SET day=?, day_count=? WHERE code=?",
                    (appmod.today(), appmod.DAILY_LIMIT, self.code))
        con.commit()
        con.close()
        item = json.dumps({"boring_en": "Boring.", "boring_my": "ပျင်းစရာ။"})
        r = c.post("/api/drill/turn",
                   data=self.audio_form(mode="upgrade", item=item),
                   content_type="multipart/form-data")
        self.assertEqual(r.status_code, 429)
        # restore
        con = sqlite3.connect(os.path.join(TMPDIR, "speak.db"))
        con.execute("UPDATE codes SET day_count=0 WHERE code=?", (self.code,))
        con.commit()
        con.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
