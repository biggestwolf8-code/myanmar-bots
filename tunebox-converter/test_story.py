"""Tests for Facebook story support in bot.py.

Run: BOT_TOKEN=dummy python3 test_story.py
Needs yt_dlp importable (PYTHONPATH to the installed package).
No network: requests.get and download_url are mocked where needed.
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("BOT_TOKEN", "dummy-test-token")

import bot  # noqa: E402


class FakeResponse:
    def __init__(self, text, url, status_code=200):
        self.text = text
        self.url = url
        self.status_code = status_code


FIXTURE_HD = (
    '<html><head><meta property="og:video" content="https://example.com/sd.mp4">'
    '</head><body>{"playable_url_quality_hd":'
    '"https:\\/\\/video.xx.fbcdn.net\\/v\\/t42.1790-2\\/12345_hd.mp4'
    '?oh=abc\\u0026oe=DEF", "playable_url":'
    '"https:\\/\\/video.xx.fbcdn.net\\/v\\/t42.1790-2\\/12345.mp4"}'
    '</body></html>'
)
FIXTURE_SD_ONLY = (
    '<html><body>{"playable_url":'
    '"https:\\/\\/video.xx.fbcdn.net\\/v\\/t42.1790-2\\/999.mp4?x=1\\u0026y=2"}'
    '</body></html>'
)
FIXTURE_OG_ONLY = (
    '<html><head><meta property="og:video:secure_url" '
    'content="https://example.com/og.mp4?x=1&amp;y=2"></head></html>'
)
FIXTURE_NONE = '<html><body>{"no_video_here": true}</body></html>'

NETSCAPE_COOKIES = (
    "# Netscape HTTP Cookie File\n"
    ".facebook.com\tTRUE\t/\tFALSE\t1999999999\tc_user\t12345\n"
)


class StoryUrlTest(unittest.TestCase):
    def test_story_urls(self):
        self.assertTrue(bot.is_facebook_story_url(
            "https://www.facebook.com/stories/1659105157517420"))
        self.assertTrue(bot.is_facebook_story_url(
            "https://www.facebook.com/stories/1659105157517420/"))
        self.assertTrue(bot.is_facebook_story_url(
            "https://m.facebook.com/stories/123/?x=1"))
        self.assertTrue(bot.is_facebook_story_url(
            "https://fb.com/stories/123456"))

    def test_not_story_urls(self):
        self.assertFalse(bot.is_facebook_story_url(
            "https://www.facebook.com/watch/?v=123"))
        self.assertFalse(bot.is_facebook_story_url(
            "https://www.facebook.com/reel/123"))
        self.assertFalse(bot.is_facebook_story_url(
            "https://www.facebook.com/stories/"))
        self.assertFalse(bot.is_facebook_story_url(
            "https://www.facebook.com/stories/abc"))
        self.assertFalse(bot.is_facebook_story_url(
            "https://www.youtube.com/watch?v=123"))
        self.assertFalse(bot.is_facebook_story_url(
            "https://www.facebook.com/username/posts/123"))


class StoryVideoUrlTest(unittest.TestCase):
    def test_prefers_hd_and_unescapes(self):
        url = bot._story_video_url(FIXTURE_HD)
        self.assertEqual(
            url,
            "https://video.xx.fbcdn.net/v/t42.1790-2/12345_hd.mp4?oh=abc&oe=DEF")

    def test_sd_fallback(self):
        url = bot._story_video_url(FIXTURE_SD_ONLY)
        self.assertEqual(
            url,
            "https://video.xx.fbcdn.net/v/t42.1790-2/999.mp4?x=1&y=2")

    def test_og_fallback(self):
        url = bot._story_video_url(FIXTURE_OG_ONLY)
        self.assertEqual(url, "https://example.com/og.mp4?x=1&y=2")

    def test_none(self):
        self.assertIsNone(bot._story_video_url(FIXTURE_NONE))


class DownloadStoryTest(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.pop("FACEBOOK_COOKIES", None)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("FACEBOOK_COOKIES", None)
        else:
            os.environ["FACEBOOK_COOKIES"] = self._old

    def test_no_cookies_says_sign_in(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src, err = bot.download_facebook_story(
                "https://www.facebook.com/stories/1659105157517420",
                tmpdir)
            self.assertIsNone(src)
            self.assertIn("FACEBOOK_COOKIES", err)

    def test_login_redirect_says_expired(self):
        os.environ["FACEBOOK_COOKIES"] = NETSCAPE_COOKIES
        with tempfile.TemporaryDirectory() as tmpdir:
            fake = FakeResponse("<html></html>",
                                "https://www.facebook.com/login.php?next=x")
            with mock.patch.object(bot.requests, "get",
                                   return_value=fake):
                src, err = bot.download_facebook_story(
                    "https://www.facebook.com/stories/1659105157517420",
                    tmpdir)
            self.assertIsNone(src)
            self.assertIn("FACEBOOK_COOKIES", err)

    def test_photo_story_says_no_video(self):
        os.environ["FACEBOOK_COOKIES"] = NETSCAPE_COOKIES
        with tempfile.TemporaryDirectory() as tmpdir:
            fake = FakeResponse(
                FIXTURE_NONE,
                "https://www.facebook.com/stories/1659105157517420")
            with mock.patch.object(bot.requests, "get",
                                   return_value=fake):
                src, err = bot.download_facebook_story(
                    "https://www.facebook.com/stories/1659105157517420",
                    tmpdir)
            self.assertIsNone(src)
            self.assertIn("photo story", err)

    def test_video_story_downloads(self):
        os.environ["FACEBOOK_COOKIES"] = NETSCAPE_COOKIES
        with tempfile.TemporaryDirectory() as tmpdir:
            fake = FakeResponse(
                FIXTURE_HD,
                "https://www.facebook.com/stories/1659105157517420")
            calls = {}

            def fake_download(url, dest):
                calls["url"] = url
                calls["dest"] = dest
                return True, ""

            with mock.patch.object(bot.requests, "get",
                                   return_value=fake), \
                    mock.patch.object(bot, "download_url",
                                      side_effect=fake_download), \
                    mock.patch.object(bot, "_url_is_public",
                                      return_value=True):
                src, title = bot.download_facebook_story(
                    "https://www.facebook.com/stories/1659105157517420",
                    tmpdir)
            self.assertEqual(
                calls["url"],
                "https://video.xx.fbcdn.net/v/t42.1790-2/12345_hd.mp4"
                "?oh=abc&oe=DEF")
            self.assertTrue(src.endswith("input.mp4"))
            self.assertEqual(title, "Facebook story 1659105157517420")

    def test_routing(self):
        self.assertEqual(
            bot.download_from_site.__code__.co_names[0], "is_facebook_story_url")
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(bot, "download_facebook_story",
                                   return_value=("/tmp/x.mp4", "t")) \
                    as m:
                src, title = bot.download_from_site(
                    "https://www.facebook.com/stories/111", tmpdir)
            m.assert_called_once()
            self.assertEqual((src, title), ("/tmp/x.mp4", "t"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
