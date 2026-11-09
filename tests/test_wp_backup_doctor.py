import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wp_backup_doctor import (  # noqa: E402
    InputError,
    audit,
    main,
    parse_input,
)

NOW = datetime(2026, 11, 5, 12, 0, 0, tzinfo=timezone.utc)
GOOD_JSON = """
[
  {"name": "site-db-2026-11-04.sql.gz", "size": 100, "modified": "2026-11-04T02:15:00+00:00", "type": "database"},
  {"name": "site-uploads-2026-11-04.zip", "size": 200, "modified": "2026-11-04T02:20:00+00:00", "type": "uploads"},
  {"name": "site-plugins-2026-11-04.zip", "size": 300, "modified": "2026-11-04T02:18:00+00:00", "type": "plugins-themes"}
]
"""


def rules(report):
    return [(f.rule, f.severity) for f in report.findings]


def run_main(argv, stdin_text=None):
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        if stdin_text is None:
            code = main(argv)
        else:
            with patch.object(sys, "stdin", io.StringIO(stdin_text)):
                code = main(argv)
    return code, stdout.getvalue()


class TestAudit(unittest.TestCase):
    def test_good_manifest_passes(self):
        report = audit(parse_input(GOOD_JSON, "test"), 7, NOW)
        self.assertEqual(report.status, "PASS")
        self.assertEqual(report.errors, 0)
        self.assertEqual(report.warnings, 0)

    def test_missing_component(self):
        entries = parse_input(
            '[{"name": "a.sql.gz", "size": 10, "modified": "2026-11-04", "type": "database"}]',
            "test",
        )
        report = audit(entries, 7, NOW)
        self.assertEqual(report.errors, 2)
        self.assertIn(("missing-component", "error"), rules(report))

    def test_empty_manifest_missing_all(self):
        report = audit(parse_input("[]", "test"), 7, NOW)
        self.assertEqual(report.errors, 3)
        self.assertEqual(report.status, "FAIL")

    def test_stale_backup_is_error(self):
        entries = parse_input(
            '[{"name": "old.sql.gz", "size": 10, "modified": "2026-10-20", "type": "database"},'
            ' {"name": "u.zip", "size": 10, "modified": "2026-11-04", "type": "uploads"},'
            ' {"name": "p.zip", "size": 10, "modified": "2026-11-04", "type": "plugins"}]',
            "test",
        )
        report = audit(entries, 7, NOW)
        self.assertIn(("stale-backup", "error"), rules(report))

    def test_max_age_override_rescues_stale(self):
        entries = parse_input(
            '[{"name": "old.sql.gz", "size": 10, "modified": "2026-10-20", "type": "database"},'
            ' {"name": "u.zip", "size": 10, "modified": "2026-11-04", "type": "uploads"},'
            ' {"name": "p.zip", "size": 10, "modified": "2026-11-04", "type": "plugins"}]',
            "test",
        )
        report = audit(entries, 30, NOW)
        self.assertEqual(report.errors, 0)

    def test_empty_file_warning_and_not_counted(self):
        entries = parse_input(
            '[{"name": "db.sql.gz", "size": 0, "modified": "2026-11-04", "type": "database"},'
            ' {"name": "u.zip", "size": 10, "modified": "2026-11-04", "type": "uploads"},'
            ' {"name": "p.zip", "size": 10, "modified": "2026-11-04", "type": "plugins"}]',
            "test",
        )
        report = audit(entries, 7, NOW)
        self.assertIn(("empty-file", "warning"), rules(report))
        self.assertIn(("missing-component", "error"), rules(report))

    def test_duplicate_name_case_insensitive(self):
        entries = parse_input(
            '[{"name": "Db.sql.gz", "size": 10, "modified": "2026-11-04", "type": "database"},'
            ' {"name": "db.SQL.gz", "size": 10, "modified": "2026-11-04", "type": "database"},'
            ' {"name": "u.zip", "size": 10, "modified": "2026-11-04", "type": "uploads"},'
            ' {"name": "p.zip", "size": 10, "modified": "2026-11-04", "type": "plugins"}]',
            "test",
        )
        report = audit(entries, 7, NOW)
        self.assertIn(("duplicate-backup", "warning"), rules(report))
        self.assertEqual(report.errors, 0)

    def test_type_aliases(self):
        entries = parse_input(
            '[{"name": "a", "size": 10, "modified": "2026-11-04", "type": "db"},'
            ' {"name": "b", "size": 10, "modified": "2026-11-04", "type": "media"},'
            ' {"name": "c", "size": 10, "modified": "2026-11-04", "type": "themes"}]',
            "test",
        )
        report = audit(entries, 7, NOW)
        self.assertEqual(report.status, "PASS")

    def test_name_inference_without_type(self):
        entries = parse_input(
            '[{"name": "site-database-2026-11-04.sql.gz", "size": 10, "modified": "2026-11-04"},'
            ' {"name": "site-uploads-2026-11-04.zip", "size": 10, "modified": "2026-11-04"},'
            ' {"name": "site-plugins-2026-11-04.zip", "size": 10, "modified": "2026-11-04"}]',
            "test",
        )
        report = audit(entries, 7, NOW)
        self.assertEqual(report.status, "PASS")

    def test_unknown_type_does_not_satisfy_component(self):
        entries = parse_input(
            '[{"name": "mystery.bin", "size": 10, "modified": "2026-11-04", "type": "full"},'
            ' {"name": "u.zip", "size": 10, "modified": "2026-11-04", "type": "uploads"},'
            ' {"name": "p.zip", "size": 10, "modified": "2026-11-04", "type": "plugins"}]',
            "test",
        )
        report = audit(entries, 7, NOW)
        self.assertIn(("unknown-component", "warning"), rules(report))
        self.assertIn(("missing-component", "error"), rules(report))

    def test_date_only_and_z_suffix(self):
        entries = parse_input(
            '[{"name": "a.sql", "size": 10, "modified": "2026-11-04", "type": "database"},'
            ' {"name": "u.zip", "size": 10, "modified": "2026-11-04T02:00:00Z", "type": "uploads"},'
            ' {"name": "p.zip", "size": 10, "modified": "2026-11-04", "type": "plugins"}]',
            "test",
        )
        report = audit(entries, 7, NOW)
        self.assertEqual(report.status, "PASS")


class TestParsing(unittest.TestCase):
    def test_listing_format(self):
        text = (
            "site-db.sql.gz 100 2026-11-04T02:15:00+00:00 database\n"
            "site-uploads.zip 200 2026-11-04 uploads\n"
            "site-plugins.zip 300 2026-11-04 plugins\n"
        )
        report = audit(parse_input(text, "test"), 7, NOW)
        self.assertEqual(report.status, "PASS")

    def test_listing_comments_and_blank_lines_ignored(self):
        text = "# comment\n\nsite-db.sql.gz 100 2026-11-04 database\n"
        entries = parse_input(text, "test")
        self.assertEqual(len(entries), 1)

    def test_json_object_with_entries_key(self):
        entries = parse_input('{"entries": []}', "test")
        self.assertEqual(entries, [])

    def test_bad_json_raises(self):
        with self.assertRaises(InputError):
            parse_input('{"entries": ', "test")

    def test_bad_date_raises(self):
        with self.assertRaises(InputError):
            parse_input(
                '[{"name": "a", "size": 1, "modified": "yesterday", "type": "database"}]',
                "test",
            )

    def test_negative_size_raises(self):
        with self.assertRaises(InputError):
            parse_input(
                '[{"name": "a", "size": -1, "modified": "2026-11-04", "type": "database"}]',
                "test",
            )

    def test_missing_name_raises(self):
        with self.assertRaises(InputError):
            parse_input(
                '[{"size": 1, "modified": "2026-11-04", "type": "database"}]',
                "test",
            )

    def test_listing_bad_size_raises(self):
        with self.assertRaises(InputError):
            parse_input("a.sql.gz big 2026-11-04 database\n", "test")


def manifest_file(directory, stale=False):
    """Write a manifest dated relative to today, so CLI tests never rot."""
    from datetime import timedelta

    today = datetime.now(timezone.utc).date().isoformat()
    old = (datetime.now(timezone.utc) - timedelta(days=20)).date().isoformat()
    db_date = old if stale else today
    entries = [
        {"name": "db.sql.gz", "size": 10, "modified": db_date, "type": "database"},
        {"name": "u.zip", "size": 10, "modified": today, "type": "uploads"},
        {"name": "p.zip", "size": 10, "modified": today, "type": "plugins"},
    ]
    if stale:
        entries = [entries[0]]
    path = Path(directory) / ("stale-manifest.json" if stale else "manifest.json")
    path.write_text(json.dumps(entries), encoding="utf-8")
    return str(path)


class TestCli(unittest.TestCase):
    def test_check_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            good = manifest_file(directory)
            bad = manifest_file(directory, stale=True)
            code, out = run_main([good, "--check"])
            self.assertEqual(code, 0)
            self.assertIn("OK:", out)
            code, out = run_main([bad, "--check"])
            self.assertEqual(code, 1)
            self.assertIn("FAIL:", out)
            code, _ = run_main([bad])
            self.assertEqual(code, 0)

    def test_warnings_only_passes_check(self):
        text = (
            '[{"name": "db.sql.gz", "size": 10, "modified": "2026-11-04", "type": "database"},'
            ' {"name": "db.sql.gz", "size": 10, "modified": "2026-11-04", "type": "database"},'
            ' {"name": "u.zip", "size": 10, "modified": "2026-11-04", "type": "uploads"},'
            ' {"name": "p.zip", "size": 10, "modified": "2026-11-04", "type": "plugins"}]'
        )
        code, out = run_main(["-", "--check"], stdin_text=text)
        self.assertEqual(code, 0)
        self.assertIn("WARN:", out)

    def test_component_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = manifest_file(directory, stale=True)
            code, out = run_main([bad, "--component", "uploads", "--check"])
            self.assertEqual(code, 1)
            self.assertIn("missing-component", out)
            self.assertNotIn("stale-backup", out)

    def test_json_output_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            good = manifest_file(directory)
            code, out = run_main([good, "--json"])
            self.assertEqual(code, 0)
            data = json.loads(out)
            self.assertEqual(data["status"], "PASS")
            self.assertEqual(data["entry_count"], 3)
            self.assertEqual(data["components"]["uploads"]["entries"], 1)

    def test_missing_file_exit_2(self):
        code, _ = run_main(["/nonexistent-manifest.json"])
        self.assertEqual(code, 2)

    def test_negative_max_age_exit_2(self):
        with tempfile.TemporaryDirectory() as directory:
            good = manifest_file(directory)
            code, _ = run_main([good, "--max-age", "-1"])
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
