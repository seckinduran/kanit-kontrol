"""Additional end-to-end reporting cases found during source inspection."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
ENTRY=ROOT/"skills/kanit-kontrol/scripts/kanit_kontrol.py"
TEMP=ROOT/"tests/_temp"

class ReportingOracle(unittest.TestCase):
    def setUp(self):
        TEMP.mkdir(exist_ok=True)
        self.fixture=tempfile.TemporaryDirectory(dir=TEMP)
        self.addCleanup(self.fixture.cleanup)
        self.root=Path(self.fixture.name)
        (self.root/"a.txt").write_bytes(b"x")
        self.manifest=self.root/"manifest.json"

    def execute(self, rows, json_mode=True):
        self.manifest.write_text(json.dumps({"files":rows}),encoding="utf-8")
        return subprocess.run([sys.executable,str(ENTRY),str(self.manifest),"--root",str(self.root),*(["--json"] if json_mode else [])],capture_output=True,cwd=ROOT,timeout=10)

    def test_valid_row_after_invalid_still_has_a_result(self):
        rows=[{"path":"../bad","sha256":"bad"},{"path":"a.txt","sha256":hashlib.sha256(b"x").hexdigest()}]
        p=self.execute(rows)
        r=json.loads(p.stdout)
        self.assertEqual((p.returncode,r["status"]),(2,"INVALID"))
        self.assertEqual([v["path"] for v in r["files"]],["../bad","a.txt"])
        self.assertEqual(r["files"][1]["status"],"OK")

    def test_human_missing_status_is_turkish(self):
        p=self.execute([{"path":"missing.txt","sha256":hashlib.sha256(b"x").hexdigest()}],json_mode=False)
        self.assertEqual(p.returncode,1)
        text=p.stdout.decode("utf-8")
        self.assertIn("Eksik",text)
        self.assertNotIn("MISSING",text)

if __name__=="__main__":
    unittest.main(verbosity=2)
