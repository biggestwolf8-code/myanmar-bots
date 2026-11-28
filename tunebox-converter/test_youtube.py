"""Tests for YouTube bot-check handling in bot.py.

Run: BOT_TOKEN=dummy python3 test_youtube.py
Needs yt_dlp importable (PYTHONPATH to the installed package).
No network: yt-dlp and the per-pass downloader are mocked where
needed; the live impersonation check is done by hand, not here.
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("BOT_TOKEN", "dummy-test-token")

import bot  # noqa: E402

CURLY_ERR = ("DownloadError('ERROR: [youtube] 9SuP4581LTA: Sign in to "
             "confirm you\u2019re not a bot. Use --cookies-from-browser "
             "or --cookies for the authentication.')")
STRAIGHT_ERR = CURLY_ERR.replace("\u2019", "'")
OTHER_ERR = ("DownloadError('ERROR: [youtube] X: This video is "
             "unavailable.')")


class FakeYDL:
    """Stand-in for yt_dlp.YoutubeDL: captures the options it was
    built with, pretends extraction worked but produced no file."""
    captured = None

    def __init__(self, opts):
        FakeYDL.captured = opts

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=True):
        return {"title": "t"}


class BotCheckMessageTest(unittest.TestCase):
    def run_media(self, err):
        with mock.patch.object(bot, "_download_with_clients",
                               return_value=(None, err)), \
                mock.patch.object(bot, "_youtube_cookies_file",
                                  return_value="/tmp/fake-cookies.txt"):
            with tempfile.TemporaryDirectory() as tmpdir:
                return bot.download_youtube_media(
                    "https://youtu.be/9SuP4581LTA", tmpdir)

    def test_curly_apostrophe(self):
        # yt-dlp's real message uses a curly apostrophe (you’re).
        # Before the 2026-11-28 fix this fell through to the generic
        # "may be unavailable" line.
        src, msg = self.run_media(CURLY_ERR)
        self.assertIsNone(src)
        self.assertIn("flagged the bot", msg)

    def test_straight_apostrophe(self):
        src, msg = self.run_media(STRAIGHT_ERR)
        self.assertIsNone(src)
        self.assertIn("flagged the bot", msg)

    def test_other_error_stays_generic(self):
        src, msg = self.run_media(OTHER_ERR)
        self.assertIsNone(src)
        self.assertIn("may be unavailable", msg)


class ImpersonateTest(unittest.TestCase):
    def test_impersonate_chrome_passed(self):
        with mock.patch.object(bot, "ffmpeg_exe",
                               return_value="/tmp/ffmpeg"), \
                mock.patch.object(bot.yt_dlp, "YoutubeDL", FakeYDL):
            with tempfile.TemporaryDirectory() as tmpdir:
                bot._download_with_clients(
                    "https://youtu.be/9SuP4581LTA", tmpdir,
                    ["android"], None)
        self.assertEqual(FakeYDL.captured.get("impersonate"), "chrome")


if __name__ == "__main__":
    unittest.main(verbosity=2)
