#!/usr/bin/env python3
"""Stubbed tests for the Biggest VPN APK wiring (no token, no network).

Run from this directory:  python3 test_vpn_app.py

Covers:
  - product page leads with the download section: Android APK, computer
    WireGuard and iPhone WireGuard buttons in that order, then trial
    and the 4 buy plans; the lead line names all three platforms
  - vpnapk callback sends the APK file
  - vpnpc / vpnios callbacks show the official WireGuard download
    instructions (verified links) and explain the .conf files arrive
    with the code on purchase / trial — no branded computer/iOS app
  - vpntrial / vpnok deliveries send 4 .conf + APK + welcome message,
    with the app section only when the code was registered with the
    vpn-api (and an admin warning when it was not)
  - vpn.provision() registers the code with the vpn-api (stubbed HTTP),
    and renew()/revoke() mirror the change there
  - vpn-api /api/admin/register + /api/login round-trip (Flask test client)
  - the shipped APK is the verified v3 build (SHA-256)
"""
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ["BOT_TOKEN"] = "test-token"
os.environ["ADMIN_CHAT_ID"] = "111"

import requests  # noqa: E402  (patched below; bot.py uses requests.post)
import vpn as vpn_mod  # noqa: E402
import bot  # noqa: E402

EXPECTED_APK_SHA256 = (
    "77ec3d190ec901805ac697f4fab74e9d0cb8000e70e39662581e3da161eea51b")
EXPECTED_APK_SIZE = 16960199


class FakeResp:
    def __init__(self, payload=None):
        self._payload = payload if payload is not None else {"ok": True}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class TelegramRecorder:
    """Stand-in for requests.post: records every Telegram call."""

    def __init__(self):
        self.calls = []  # (method, data, files_info)

    def post(self, url, data=None, files=None, json=None, timeout=None):
        method = url.rsplit("/", 1)[-1]
        files_info = {}
        if files:
            for key, val in files.items():
                name = val[0]
                body = val[1]
                content = body.read() if hasattr(body, "read") else body
                files_info[key] = (name, len(content))
        self.calls.append((method, data or json or {}, files_info))
        return FakeResp()

    def documents(self):
        return [c for c in self.calls if c[0] == "sendDocument"]

    def messages(self):
        return [c for c in self.calls if c[0] == "sendMessage"]

    def edits(self):
        return [c for c in self.calls if c[0] == "editMessageText"]


def fake_result(app_registered=True):
    configs = {}
    for srv in ("singapore", "japan", "uk", "usa"):
        configs[srv] = ("[Interface]\nPrivateKey = dGVzdA==\nAddress = "
                        f"10.8.0.9/32\n\n[Peer]\nPublicKey = c2VydmVy\n"
                        "Endpoint = 149.28.150.78:443\nAllowedIPs = 0.0.0.0/0\n")
    return {"code": "VPN-123456", "configs": configs,
            "expires_at": "2026-12-18T00:00:00+00:00",
            "plan": "1 Month / 1 Device", "app_registered": app_registered}


class BotApkTests(unittest.TestCase):
    def setUp(self):
        self.tg = TelegramRecorder()
        self.patch_post = mock.patch.object(requests, "post",
                                            side_effect=self.tg.post)
        self.patch_post.start()
        self.addCleanup(self.patch_post.stop)

    def _callback(self, data, chat_id="123"):
        bot.handle_callback({
            "id": "cb1", "data": data,
            "message": {"chat": {"id": int(chat_id)}, "message_id": 5},
        })

    def test_product_page_has_apk_button(self):
        kb = bot.kb_vpn_buy("Biggest VPN")
        callbacks = [b["callback_data"]
                     for row in kb["inline_keyboard"] for b in row]
        self.assertIn("vpnapk", callbacks)
        texts = [b["text"] for row in kb["inline_keyboard"] for b in row]
        self.assertIn("📱 Android — Download the app (APK)", texts)
        # trial + 4 buy buttons + back still present
        self.assertIn("vpntrial", callbacks)
        self.assertEqual(sum(1 for c in callbacks
                             if c.startswith("vpnbuy:")), 4)

    def test_product_page_download_buttons_in_order(self):
        kb = bot.kb_vpn_buy("Biggest VPN")
        rows = kb["inline_keyboard"]
        self.assertEqual([r[0]["callback_data"] for r in rows[:4]],
                         ["vpnapk", "vpnpc", "vpnios", "vpntrial"])
        self.assertEqual([r[0]["text"] for r in rows[:3]],
                         ["📱 Android — Download the app (APK)",
                          "💻 Computer — Get WireGuard",
                          "🍎 iPhone — Get WireGuard"])
        # 4 buy plans, then Back
        self.assertEqual(sum(1 for r in rows
                             if r[0]["callback_data"].startswith("vpnbuy:")),
                         4)
        self.assertEqual(rows[-1][0]["text"], "⬅️ Back")

    def test_product_page_lead_line_names_three_platforms(self):
        ci = bot.CATS.index("VPN")
        j = bot.PRODUCTS["VPN"].index("Biggest VPN")
        self._callback(f"p:{ci}:{j}")
        edits = self.tg.edits()
        self.assertEqual(len(edits), 1)
        text = edits[0][1]["text"]
        self.assertIn("⬇️ Download Biggest VPN — for Android, iPhone "
                      "and computers:", text)
        self.assertIn("4 countries included: Singapore, Japan, UK, USA.",
                      text)

    def test_vpnpc_callback_shows_computer_message(self):
        self._callback("vpnpc")
        self.assertEqual(len(self.tg.documents()), 0)  # no APK on this path
        self.assertEqual(len(self.tg.messages()), 0)  # edit, not a new msg
        edits = self.tg.edits()
        self.assertEqual(len(edits), 1)
        text = edits[0][1]["text"]
        self.assertIn("https://www.wireguard.com/install/", text)
        for word in ("Windows", "macOS", "Linux", ".conf",
                     "free trial", "official WireGuard app"):
            self.assertIn(word, text)
        # no branded computer app is claimed
        self.assertIn("no separate Biggest VPN app for computers", text)
        self.assertNotIn("BiggestVPN.apk", text)
        # the product-page keyboard comes back with the download buttons
        kb = edits[0][1]["reply_markup"]["inline_keyboard"]
        callbacks = [b["callback_data"] for row in kb for b in row]
        self.assertEqual(callbacks[:3], ["vpnapk", "vpnpc", "vpnios"])

    def test_vpnios_callback_shows_iphone_message(self):
        self._callback("vpnios")
        self.assertEqual(len(self.tg.documents()), 0)
        self.assertEqual(len(self.tg.messages()), 0)
        edits = self.tg.edits()
        self.assertEqual(len(edits), 1)
        text = edits[0][1]["text"]
        # official WireGuard iOS app on the App Store (verified link)
        self.assertIn("https://itunes.apple.com/us/app/wireguard/"
                      "id1441195209?ls=1&mt=8", text)
        for word in ("App Store", ".conf", "free trial",
                     "official WireGuard app"):
            self.assertIn(word, text)
        # no branded iPhone app is claimed
        self.assertIn("no separate Biggest VPN app for iPhone", text)
        self.assertNotIn("BiggestVPN.apk", text)
        kb = edits[0][1]["reply_markup"]["inline_keyboard"]
        callbacks = [b["callback_data"] for row in kb for b in row]
        self.assertEqual(callbacks[:3], ["vpnapk", "vpnpc", "vpnios"])

    def test_vpnapk_callback_sends_apk(self):
        self._callback("vpnapk")
        docs = self.tg.documents()
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0][2]["document"][0], "BiggestVPN.apk")
        self.assertEqual(docs[0][2]["document"][1], EXPECTED_APK_SIZE)
        self.assertEqual(len(self.tg.edits()), 1)
        self.assertIn("App sent", self.tg.edits()[0][1]["text"])

    def test_send_vpn_configs_registered(self):
        bot.send_vpn_configs("123", fake_result(app_registered=True))
        docs = self.tg.documents()
        # 4 .conf files + 1 APK
        self.assertEqual(len(docs), 5)
        names = [d[2]["document"][0] for d in docs]
        self.assertEqual(names[:4], ["BiggestVPN-Singapore.conf",
                                     "BiggestVPN-Japan.conf",
                                     "BiggestVPN-UK.conf",
                                     "BiggestVPN-USA.conf"])
        self.assertEqual(names[4], "BiggestVPN.apk")
        msgs = self.tg.messages()
        self.assertEqual(len(msgs), 1)  # welcome only, no admin warning
        text = msgs[0][1]["text"]
        self.assertIn("📱 EASIER WAY — Biggest VPN app", text)
        self.assertIn("VPN-123456", text)
        self.assertIn("Android-only", text)
        self.assertIn("Install the free", text)  # WireGuard fallback kept
        self.assertNotIn("MPT", text)  # no claim about MPT either way

    def test_send_vpn_configs_unregistered(self):
        bot.send_vpn_configs("123", fake_result(app_registered=False))
        docs = self.tg.documents()
        self.assertEqual(len(docs), 5)  # APK still sent with the .conf files
        msgs = self.tg.messages()
        welcome = [m for m in msgs if m[1].get("chat_id") == "123"]
        self.assertEqual(len(welcome), 1)
        self.assertNotIn("EASIER WAY", welcome[0][1]["text"])
        self.assertIn("Install the free", welcome[0][1]["text"])
        admin = [m for m in msgs if m[1].get("chat_id") == "111"]
        self.assertEqual(len(admin), 1)
        self.assertIn("NOT registered with the app API",
                      admin[0][1]["text"])
        self.assertIn("VPN-123456", admin[0][1]["text"])

    def test_welcome_template_placeholders(self):
        self.assertEqual(bot.VPN_WELCOME_MSG.count("{app_section}"), 1)
        for ph in ("{plan}", "{code}", "{expires}"):
            self.assertIn(ph, bot.VPN_WELCOME_MSG)
        rendered = bot.VPN_WELCOME_MSG.format(
            plan="1 Month / 1 Device", code="VPN-123456",
            expires="2026-12-18", app_section="")
        self.assertIn("🎉 Your Biggest VPN is ready!", rendered)
        self.assertNotIn("{app_section}", rendered)
        self.assertNotIn("EASIER WAY", rendered)

    def test_trial_delivery_includes_apk(self):
        result = fake_result(app_registered=True)
        with mock.patch.object(vpn_mod, "has_used_trial",
                               return_value=False), \
             mock.patch.object(vpn_mod, "mark_trial_used"), \
             mock.patch.object(vpn_mod, "provision",
                               return_value=(True, result)):
            self._callback("vpntrial")
        docs = self.tg.documents()
        self.assertEqual(len(docs), 5)
        self.assertEqual(docs[4][2]["document"][0], "BiggestVPN.apk")
        texts = [m[1]["text"] for m in self.tg.messages()]
        self.assertTrue(any("FREE trial is live" in t for t in texts))
        self.assertTrue(any("EASIER WAY" in t for t in texts))

    def test_paid_delivery_includes_apk(self):
        result = fake_result(app_registered=True)
        with mock.patch.object(vpn_mod, "provision",
                               return_value=(True, result)), \
             mock.patch.object(bot, "load_vpn_orders",
                               return_value={"999": {"plan": "1 Month / 1 Device"}}), \
             mock.patch.object(bot, "save_vpn_orders"):
            self._callback("vpnok:999:1 Month / 1 Device", chat_id="111")
        docs = self.tg.documents()
        self.assertEqual(len(docs), 5)
        self.assertEqual(docs[4][2]["document"][0], "BiggestVPN.apk")
        texts = [m[1]["text"] for m in self.tg.messages()]
        self.assertTrue(any("EASIER WAY" in t for t in texts))


class VpnApiRegistrationTests(unittest.TestCase):
    """provision()/renew()/revoke() talk to the vpn-api (stubbed HTTP)."""

    def setUp(self):
        self.store = {}
        self.api_calls = []
        vpn_mod.VPN_API_ADMIN_SECRET = "dummy-admin-secret-for-tests"
        self.p_load = mock.patch.object(vpn_mod, "_load",
                                        side_effect=lambda: dict(self.store))
        # _save replaces the whole store; emulate with a plain dict copy.
        self.p_save = mock.patch.object(
            vpn_mod, "_save",
            side_effect=lambda d: (self.store.clear(), self.store.update(d)))
        self.p_load.start()
        self.p_save.start()
        self.addCleanup(self.p_load.stop)
        self.addCleanup(self.p_save.stop)
        self.p_ssh = mock.patch.object(vpn_mod, "_ssh",
                                       side_effect=self._fake_ssh)
        self.p_ssh.start()
        self.addCleanup(self.p_ssh.stop)
        self.p_urlopen = mock.patch("urllib.request.urlopen",
                                    side_effect=self._fake_urlopen)
        self.p_urlopen.start()
        self.addCleanup(self.p_urlopen.stop)

    @staticmethod
    def _fake_ssh(host, command, timeout=30):
        if "public-key" in command:
            return True, "c2VydmVycHVi"
        if "allowed-ips" in command:
            return True, ""
        if "wg set wg0 peer" in command:
            return True, "OK"
        return False, "unexpected command"

    def _fake_urlopen(self, req, timeout=None):
        import urllib.error
        payload = json.loads(req.data.decode())
        self.api_calls.append((req.full_url, payload))
        body = json.dumps({"ok": True}).encode()
        resp = mock.MagicMock()
        resp.read.return_value = body
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    def test_provision_registers_code_with_api(self):
        ok, result = vpn_mod.provision("Test User", 123,
                                       "1 Month / 1 Device")
        self.assertTrue(ok)
        self.assertTrue(result["app_registered"])
        self.assertEqual(len(self.api_calls), 1)
        url, payload = self.api_calls[0]
        self.assertTrue(url.endswith("/api/admin/register"))
        self.assertEqual(payload["code"], result["code"])
        self.assertEqual(set(payload["configs"]), {
            "singapore", "japan", "uk", "usa"})
        self.assertEqual(payload["trial"], False)

    def test_provision_still_succeeds_when_api_down(self):
        with mock.patch("urllib.request.urlopen",
                        side_effect=Exception("no route")):
            ok, result = vpn_mod.provision("Test User", 123,
                                           "1 Month / 1 Device")
        self.assertTrue(ok)  # .conf delivery must not break
        self.assertFalse(result["app_registered"])

    def test_renew_and_revoke_mirror_to_api(self):
        ok, result = vpn_mod.provision("Test User", 123,
                                       "1 Month / 1 Device")
        self.assertTrue(ok)
        code = result["code"]
        self.api_calls.clear()
        ok, _ = vpn_mod.renew(code, 30)
        self.assertTrue(ok)
        self.assertTrue(any(u.endswith("/api/admin/renew")
                            for u, _ in self.api_calls))
        self.api_calls.clear()
        ok, _ = vpn_mod.revoke(code)
        self.assertTrue(ok)
        self.assertTrue(any(u.endswith("/api/admin/revoke")
                            for u, _ in self.api_calls))


class VpnApiEndpointTests(unittest.TestCase):
    """Real Flask app: register a bot-issued code, then log in with it."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="vpn-api-test-")
        os.environ["DATA_DIR"] = cls.tmp
        os.environ["ADMIN_SECRET"] = "dummy-admin-secret-for-tests"
        spec = importlib.util.spec_from_file_location(
            "vpn_api_app", os.path.join(HERE, "..", "vpn-api", "app.py"))
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)
        # revoke() shells out over SSH; stub it (no network in tests).
        cls.mod._ssh_exec = lambda host, cmd, timeout=30: (True, "OK")
        cls.client = cls.mod.app.test_client()

    def test_register_then_login_round_trip(self):
        code = "VPN-123456"
        configs = {"singapore": "[Interface]\nPrivateKey = dGVzdA==\n",
                   "japan": "[Interface]\nPrivateKey = dGVzdA==\n",
                   "uk": "[Interface]\nPrivateKey = dGVzdA==\n",
                   "usa": "[Interface]\nPrivateKey = dGVzdA==\n"}
        r = self.client.post("/api/admin/register", json={
            "admin_secret": "dummy-admin-secret-for-tests",
            "code": code, "name": "Test User", "telegram_id": 123,
            "expires_at": "2026-12-18T00:00:00+00:00",
            "configs": configs, "client_pub": "dGVzdA==",
            "trial": False})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

        r = self.client.post("/api/login",
                             json={"code": code, "device_id": "dev1"})
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["configs"], configs)
        self.assertGreater(data["days_left"], 0)

        # unknown code is refused
        r = self.client.post("/api/login",
                             json={"code": "VPN-999999", "device_id": "dev1"})
        self.assertEqual(r.status_code, 401)

        # renew extends the expiry the app sees
        r = self.client.post("/api/admin/renew", json={
            "admin_secret": "dummy-admin-secret-for-tests",
            "code": code, "days": 30})
        self.assertEqual(r.status_code, 200)

        # revoke removes the record: login fails again
        r = self.client.post("/api/admin/revoke", json={
            "admin_secret": "dummy-admin-secret-for-tests", "code": code})
        self.assertEqual(r.status_code, 200)
        r = self.client.post("/api/login",
                             json={"code": code, "device_id": "dev1"})
        self.assertEqual(r.status_code, 401)

    def test_register_requires_admin_secret(self):
        r = self.client.post("/api/admin/register", json={
            "admin_secret": "wrong", "code": "VPN-000000",
            "configs": {"singapore": "x"},
            "expires_at": "2026-12-18T00:00:00+00:00"})
        self.assertEqual(r.status_code, 403)
        r = self.client.post("/api/admin/register", json={
            "admin_secret": "dummy-admin-secret-for-tests",
            "code": "VPN-000001", "configs": {},
            "expires_at": "2026-12-18T00:00:00+00:00"})
        self.assertEqual(r.status_code, 400)


class ApkFileTests(unittest.TestCase):
    def test_shipped_apk_is_verified_v3(self):
        path = os.path.join(HERE, "biggest-vpn.apk")
        self.assertTrue(os.path.exists(path), "biggest-vpn.apk missing")
        h = hashlib.sha256()
        size = 0
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
                size += len(chunk)
        self.assertEqual(size, EXPECTED_APK_SIZE)
        self.assertEqual(h.hexdigest(), EXPECTED_APK_SHA256)

    def test_no_secrets_in_changed_files(self):
        for name in ("bot.py", "vpn.py"):
            with open(os.path.join(HERE, name), encoding="utf-8") as f:
                text = f.read()
            self.assertNotIn("PRIVATE KEY", text)
            self.assertNotIn("dummy-admin-secret-for-tests", text)
        with open(os.path.join(HERE, "..", "vpn-api", "app.py"),
                  encoding="utf-8") as f:
            api_text = f.read()
        self.assertNotIn("dummy-admin-secret-for-tests", api_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
