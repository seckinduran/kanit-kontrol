"""Frozen independent black-box oracle for Kanit Kontrol. No network or OS services."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "skills" / "kanit-kontrol" / "scripts" / "kanit_kontrol.py"
TEMP = ROOT / "tests" / "_temp"

def digest(data):
    return hashlib.sha256(data).hexdigest()

class EvidenceOracle(unittest.TestCase):
    def setUp(self):
        TEMP.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=TEMP)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest = self.root / "manifest.json"

    def save(self, rows):
        self.manifest.write_text(json.dumps({"files": rows}, ensure_ascii=False), encoding="utf-8")

    def row(self, relative, data, **extra):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return {"path": relative, "sha256": digest(data), **extra}

    def run_cli(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", [str(ENTRY), str(self.manifest), "--root", str(self.root), "--json"]), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                runpy.run_path(str(ENTRY), run_name="__main__")
                code = 0
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after, "Verification must not change input files")
        try:
            report = json.loads(out.getvalue())
        except Exception:
            self.fail("stdout must be one valid JSON report: " + repr(out.getvalue()) + " stderr=" + repr(err.getvalue()))
        self.assertIsInstance(report, dict)
        self.assertNotIn(str(self.root), json.dumps(report, ensure_ascii=False), "Report must use relative paths")
        return code, report, err.getvalue()

    def test_exact_unicode_and_binary(self):
        a = self.row("alt/İş ğ.txt", "Türkçe\n".encode(), bytes=9)
        a["bytes"] = len("Türkçe\n".encode())
        b = self.row("binary.bin", bytes(range(256)), bytes=256)
        self.save([a,b])
        code, report, _ = self.run_cli()
        self.assertEqual((code, report["status"], report["summary"]["ok"]), (0,"OK",2))
        self.assertIn("doğrulan", report["message"].lower())
        self.assertTrue(all(x["status"] == "OK" for x in report["files"]))

    def test_same_length_tamper(self):
        a = self.row("a.txt", b"old")
        self.save([a])
        (self.root / "a.txt").write_bytes(b"new")
        code, report, _ = self.run_cli()
        self.assertEqual((code, report["status"], report["files"][0]["status"]), (1,"FAILED","MISMATCH"))

    def test_missing_file(self):
        self.save([{"path":"missing.txt","sha256":digest(b"x")}])
        code, report, _ = self.run_cli()
        self.assertEqual((code, report["status"], report["files"][0]["status"]), (1,"FAILED","MISSING"))

    def test_size_mismatch_is_failure(self):
        a = self.row("a.txt", b"same", bytes=999)
        self.save([a])
        code, report, _ = self.run_cli()
        self.assertEqual((code, report["status"], report["files"][0]["status"]), (1,"FAILED","SIZE_MISMATCH"))

    def test_parent_escape_invalid(self):
        self.save([{"path":"../private.txt","sha256":digest(b"x")}])
        code, report, _ = self.run_cli()
        self.assertEqual((code, report["status"]), (2,"INVALID"))

    def test_absolute_and_windows_paths_invalid(self):
        for name in ["/absolute.txt", "C:/private.txt", "C:\\private.txt", "\\\\server\\share\\private.txt"]:
            with self.subTest(name=name):
                self.save([{"path":name,"sha256":digest(b"x")}])
                code, report, _ = self.run_cli()
                self.assertEqual((code, report["status"]), (2,"INVALID"))

    def test_duplicate_path_invalid(self):
        a = self.row("a.txt", b"x")
        self.save([a,a])
        code, report, _ = self.run_cli()
        self.assertEqual((code, report["status"]), (2,"INVALID"))

    def test_bad_hash_and_byte_types_invalid(self):
        for extra in [{"sha256":"wrong"},{"sha256":None},{"bytes":True},{"bytes":-1},{"bytes":"1"}]:
            with self.subTest(extra=extra):
                a = self.row("a.txt", b"x")
                a.update(extra)
                self.save([a])
                code, report, _ = self.run_cli()
                self.assertEqual((code, report["status"]), (2,"INVALID"))

    def test_raw_line_endings_not_silently_accepted(self):
        self.row("a.txt", b"a\r\nb\r\n")
        self.save([{"path":"a.txt","sha256":digest(b"a\nb\n")}])
        code, report, _ = self.run_cli()
        self.assertEqual((code, report["status"], report["files"][0]["status"]), (1,"FAILED","MISMATCH"))

    def test_invalid_json_reports_invalid(self):
        self.manifest.write_text("{broken", encoding="utf-8")
        code, report, _ = self.run_cli()
        self.assertEqual((code, report["status"]), (2,"INVALID"))

    def test_empty_or_missing_files_never_green(self):
        for value in [{"files":[]},{},{"files":"not-list"}]:
            with self.subTest(value=value):
                self.manifest.write_text(json.dumps(value), encoding="utf-8")
                code, report, _ = self.run_cli()
                self.assertEqual((code, report["status"]), (2,"INVALID"))

    def test_catalogue_additional_metadata_compatible(self):
        a = self.row("a.txt", b"x", bytes=1, kind="RAW_EVIDENCE")
        self.manifest.write_text(json.dumps({"kind":"REFERENCE_INDEX","root":"ignored-untrusted-other-root","files":[a],"counts":{"listedFiles":1}}), encoding="utf-8")
        code, report, _ = self.run_cli()
        self.assertEqual((code, report["status"],report["summary"]["ok"]), (0,"OK",1))

if __name__ == "__main__":
    unittest.main(verbosity=2)
