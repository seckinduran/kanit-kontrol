"""Complete CLI error-path language and visible-feedback regressions."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
ENTRY=ROOT/"skills/kanit-kontrol/scripts/kanit_kontrol.py"

class CliErrorOracle(unittest.TestCase):
    def invoke(self,args):
        return subprocess.run([sys.executable,str(ENTRY),*args],cwd=ROOT,capture_output=True,timeout=10)

    def assert_english_invalid(self,args):
        p=self.invoke(args)
        r=json.loads(p.stdout)
        self.assertEqual((p.returncode,r["status"],r["summary"]),(2,"INVALID",{"total":0,"ok":0}))
        self.assertIn("invalid",r["message"].lower())
        self.assertNotIn("Geçersiz",r["message"])

    def test_missing_root_human_has_turkish_explanation(self):
        p=self.invoke(["manifest.json"])
        self.assertEqual(p.returncode,2)
        text=(p.stdout+p.stderr).decode("utf-8")
        self.assertIn("Geçersiz",text)

    def test_missing_root_json_preserves_english(self):
        self.assert_english_invalid(["manifest.json","--json","--lang","en"])

    def test_unknown_argument_json_preserves_english(self):
        self.assert_english_invalid(["manifest.json","--root",".","--json","--lang","en","--unknown"])

    def test_inline_language_json_preserves_english(self):
        self.assert_english_invalid(["manifest.json","--root",".","--json","--lang=en","--unknown"])

if __name__=="__main__":
    unittest.main(verbosity=2)
