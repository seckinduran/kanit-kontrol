"""Real CLI regressions for duplicate resolved-path aliases."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
ENTRY=ROOT/"skills/kanit-kontrol/scripts/kanit_kontrol.py"
TEMP=ROOT/"tests/_temp"

class PathAliasOracle(unittest.TestCase):
    def check_alias(self, first, alias):
        TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEMP) as folder:
            root=Path(folder)
            (root/"a.txt").write_bytes(b"x")
            digest=hashlib.sha256(b"x").hexdigest()
            manifest=root/"manifest.json"
            manifest.write_text(json.dumps({"files":[{"path":first,"sha256":digest},{"path":alias,"sha256":digest}]}),encoding="utf-8")
            before={p.name:p.read_bytes() for p in root.iterdir()}
            p=subprocess.run([sys.executable,str(ENTRY),str(manifest),"--root",str(root),"--json"],capture_output=True,cwd=ROOT,timeout=10)
            after={p.name:p.read_bytes() for p in root.iterdir()}
            self.assertEqual(before,after)
            r=json.loads(p.stdout)
            self.assertEqual((p.returncode,r["status"]),(2,"INVALID"))
            self.assertEqual(r["summary"],{"total":2,"ok":1})
            self.assertEqual(r["files"][1]["status"],"INVALID_PATH")

    def test_dot_alias_is_duplicate(self):
        self.check_alias("a.txt","./a.txt")

    def test_repeated_separator_alias_is_duplicate(self):
        self.check_alias("a.txt",".//a.txt")

    def test_distinct_files_with_same_hash_remain_valid(self):
        TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEMP) as folder:
            root=Path(folder)
            for name in ("a.txt","b.txt"):
                (root/name).write_bytes(b"x")
            digest=hashlib.sha256(b"x").hexdigest()
            manifest=root/"manifest.json"
            manifest.write_text(json.dumps({"files":[{"path":n,"sha256":digest} for n in ("a.txt","b.txt")]}),encoding="utf-8")
            p=subprocess.run([sys.executable,str(ENTRY),str(manifest),"--root",str(root),"--json"],capture_output=True,cwd=ROOT,timeout=10)
            r=json.loads(p.stdout)
            self.assertEqual((p.returncode,r["status"],r["summary"]),(0,"OK",{"total":2,"ok":2}))

    @unittest.skipUnless(os.name=="nt","Windows case-insensitive path semantics")
    def test_windows_case_alias_is_duplicate(self):
        self.check_alias("a.txt","A.TXT")

if __name__=="__main__":
    unittest.main(verbosity=2)
