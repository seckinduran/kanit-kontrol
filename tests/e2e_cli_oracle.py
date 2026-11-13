"""Independent complete CLI scenarios. Frozen oracle remains unchanged."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "skills/kanit-kontrol/scripts/kanit_kontrol.py"
TEMP = ROOT / "tests/_temp"

class CliEndToEnd(unittest.TestCase):
    def setUp(self):
        TEMP.mkdir(exist_ok=True)
        self.fixture = tempfile.TemporaryDirectory(dir=TEMP)
        self.addCleanup(self.fixture.cleanup)
        self.root = Path(self.fixture.name)
        self.data = b"x"
        (self.root / "a.txt").write_bytes(self.data)
        self.row = {"path":"a.txt", "sha256":hashlib.sha256(self.data).hexdigest()}
        self.manifest = self.root / "manifest.json"

    def execute(self, rows=None, json_output=True, extra=()):
        self.manifest.write_text(json.dumps({"files": rows if rows is not None else [self.row]}), encoding="utf-8")
        before = {p.name:p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        result = subprocess.run([sys.executable,str(ENTRY),str(self.manifest),"--root",str(self.root),*(["--json"] if json_output else []),*extra],cwd=ROOT,capture_output=True,timeout=10)
        after = {p.name:p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        self.assertEqual(before,after)
        return result

    def test_human_output_is_visible(self):
        p = self.execute(json_output=False)
        self.assertEqual(p.returncode,0)
        self.assertTrue(p.stdout.strip(),"Normal user path must display a result")

    def test_help_is_success_not_invalid(self):
        p = subprocess.run([sys.executable,str(ENTRY),"--help"],cwd=ROOT,capture_output=True,timeout=10)
        self.assertEqual(p.returncode,0)
        self.assertIn(b"Kan",p.stdout)
        self.assertNotIn(b'"status": "INVALID"',p.stdout)

    def test_invalid_manifest_priority_survives_later_missing_file(self):
        missing={"path":"missing.txt","sha256":hashlib.sha256(b"x").hexdigest()}
        p=self.execute([{"path":"../bad","sha256":"not-a-hash"},missing])
        report=json.loads(p.stdout)
        self.assertEqual((p.returncode,report["status"]),(2,"INVALID"))

    def test_hash_is_exact_hex_not_int_parser_extensions(self):
        self.row["sha256"]="a"*31+"_"+"a"*32
        p=self.execute()
        report=json.loads(p.stdout)
        self.assertEqual((p.returncode,report["status"]),(2,"INVALID"))

    def test_explicit_null_bytes_is_invalid(self):
        self.row["bytes"]=None
        p=self.execute()
        report=json.loads(p.stdout)
        self.assertEqual((p.returncode,report["status"]),(2,"INVALID"))

    def test_english_selection_reaches_reply(self):
        p=self.execute(extra=("--lang","en"))
        report=json.loads(p.stdout)
        self.assertEqual((p.returncode,report["status"]),(0,"OK"))
        self.assertIn("verified",report["message"].lower())

if __name__=="__main__":
    unittest.main(verbosity=2)
