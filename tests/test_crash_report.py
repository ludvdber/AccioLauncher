"""Tests pour src/ui/crash_dialog.py — parties pures (rapport, scrub, URL)."""

from pathlib import Path

from src.core.config import APP_VERSION
from src.ui.crash_dialog import build_crash_report, github_issue_url, scrub_user_paths


class TestScrubUserPaths:
    def test_home_replaced(self):
        home = str(Path.home())
        assert "~" in scrub_user_paths(f"Erreur dans {home}\\Games\\x.log")
        assert home not in scrub_user_paths(f"Erreur dans {home}\\Games\\x.log")

    def test_forward_slash_variant(self):
        home_fwd = str(Path.home()).replace("\\", "/")
        assert home_fwd not in scrub_user_paths(f"path={home_fwd}/Games")

    def test_other_text_untouched(self):
        assert scrub_user_paths("rien à voir") == "rien à voir"


class TestBuildCrashReport:
    def test_contains_version_and_error(self):
        report = build_crash_report("Traceback...\nValueError: boom")
        assert APP_VERSION in report
        assert "ValueError: boom" in report

    def test_log_tail_included_and_scrubbed(self):
        home = str(Path.home())
        report = build_crash_report("err", log_tail=f"DEBUG ouvert {home}\\f.7z")
        assert "Log" in report
        assert home not in report


class TestGithubIssueUrl:
    def test_url_shape(self):
        url = github_issue_url("rapport court")
        assert url.startswith("https://github.com/ludvdber/AccioLauncher/issues/new?title=")
        assert "body=" in url

    def test_long_report_truncated(self):
        url = github_issue_url("x" * 10_000)
        # L'URL doit rester sous la limite pratique des navigateurs
        assert len(url) < 2600
