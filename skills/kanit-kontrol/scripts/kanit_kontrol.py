#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Kanıt Kontrol - Çevrimdışı ve Salt Okunur Dosya Bütünlüğü Doğrulama Aracı
Standard library (Python 3.10+) only.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path


def get_translation(lang: str, key: str, **kwargs) -> str:
    messages = {
        "tr": {
            "all_verified": "Tüm dosyalar başarıyla doğrulandı.",
            "some_failed": "Bazı dosyalarda bütünlük uyumsuzluğu veya eksiklik tespit edildi.",
            "invalid_manifest": "Geçersiz manifest dosyası, eksik veya hatalı yapı.",
            "cli_summary": "Kanıt Kontrol Sonucu: {status} | Toplam: {total}, Başarılı: {ok}",
            "file_line": "  - {path}: {status}",
        },
        "en": {
            "all_verified": "All files verified successfully.",
            "some_failed": "Integrity mismatch or missing files detected.",
            "invalid_manifest": "Invalid manifest file or structure.",
            "cli_summary": "Evidence Check Result: {status} | Total: {total}, OK: {ok}",
            "file_line": "  - {path}: {status}",
        },
    }
    lang_dict = messages.get(lang, messages["tr"])
    msg = lang_dict.get(key, key)
    if kwargs:
        try:
            return msg.format(**kwargs)
        except Exception:
            return msg
    return msg


def configure_utf8_stdout():
    for stream_obj in (sys.stdout, sys.stderr):
        if stream_obj and hasattr(stream_obj, "reconfigure"):
            try:
                stream_obj.reconfigure(encoding="utf-8")
            except Exception:
                pass


def compute_sha256(file_path: Path) -> str:
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()


def main():
    configure_utf8_stdout()

    parser = argparse.ArgumentParser(description="Kanıt Kontrol - SHA256 Bütünlük Denetleyicisi")
    parser.add_argument("manifest", type=str, nargs="?", help="Manifest JSON dosya yolu")
    parser.add_argument("--root", type=str, help="Kök dizin")
    parser.add_argument("--json", action="store_true", help="Yalnız JSON çıktı üret")
    parser.add_argument("--lang", type=str, default="tr", choices=["tr", "en"], help="Dil seçimi (tr|en)")

    try:
        # sys.argv kontrolü ile --help argümanının varlığını doğrudan yakalayalım
        if "--help" in sys.argv or "-h" in sys.argv:
            parser.print_help()
            sys.exit(0)

        args = parser.parse_args()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        if code == 0:
            sys.exit(0)
        error_report = {
            "status": "INVALID",
            "message": "Geçersiz argüman veya komut satırı hatası.",
            "summary": {"total": 0, "ok": 0},
            "files": []
        }
        if "--json" in sys.argv:
            print(json.dumps(error_report, ensure_ascii=False))
        sys.exit(2)

    # Manifest veya root eksikse argparse eksik argüman hatası verir ama emin olalım
    if not args.manifest or not args.root:
        error_report = {
            "status": "INVALID",
            "message": "Geçersiz argüman veya komut satırı hatası.",
            "summary": {"total": 0, "ok": 0},
            "files": []
        }
        if args.json:
            print(json.dumps(error_report, ensure_ascii=False))
        sys.exit(2)

    lang = args.lang
    root_path = Path(args.root).resolve()
    manifest_path = Path(args.manifest)

    report = {
        "status": "INVALID",
        "message": get_translation(lang, "invalid_manifest"),
        "summary": {"total": 0, "ok": 0},
        "files": []
    }

    # 1. Manifest yükleme ve JSON kontrolü
    try:
        if not manifest_path.is_file():
            raise ValueError("Manifest dosyası bulunamadı.")
        content = manifest_path.read_text(encoding="utf-8")
        data = json.loads(content)
    except Exception:
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            print(json.dumps(report, ensure_ascii=False))
        sys.exit(2)

    if not isinstance(data, dict):
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            print(json.dumps(report, ensure_ascii=False))
        sys.exit(2)

    files_list = data.get("files")
    if not isinstance(files_list, list) or len(files_list) == 0:
        report["status"] = "INVALID"
        report["message"] = get_translation(lang, "invalid_manifest")
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            print(json.dumps(report, ensure_ascii=False))
        sys.exit(2)

    seen_paths = set()
    file_results = []
    total_files = len(files_list)
    ok_count = 0
    # Kapsamlı durum önceliği: INVALID > FAILED > OK
    overall_status = "OK"

    for item in files_list:
        if not isinstance(item, dict):
            overall_status = "INVALID"
            file_results.append({"path": str(item), "status": "INVALID_PATH"})
            continue

        rel_path_str = item.get("path")
        expected_sha = item.get("sha256")

        # 'bytes' alanı dict içinde VAR mi yok mu kontrolü (anahtar varsa ve değeri null ise geçersizdir)
        has_bytes_key = "bytes" in item
        expected_bytes = item.get("bytes")

        # Yol string kontrolü ve duplicate kontrolü
        if not isinstance(rel_path_str, str) or not rel_path_str.strip():
            overall_status = "INVALID"
            file_results.append({"path": str(rel_path_str), "status": "INVALID_PATH"})
            continue

        if rel_path_str in seen_paths:
            overall_status = "INVALID"
            file_results.append({"path": rel_path_str, "status": "INVALID_PATH"})
            continue
        seen_paths.add(rel_path_str)

        # Path traversal, Absolute, Windows drive / UNC kontrolleri
        if (
            rel_path_str.startswith("/")
            or rel_path_str.startswith("\\")
            or ":" in rel_path_str
            or ".." in Path(rel_path_str).parts
            or Path(rel_path_str).is_absolute()
        ):
            overall_status = "INVALID"
            file_results.append({"path": rel_path_str, "status": "INVALID_PATH"})
            continue

        # Hash kontrolü (Tam 64 hex karakter olmalı, alt/üst harf, rakam; underscore, artı veya boşluk olmamalı)
        if not isinstance(expected_sha, str) or not re.fullmatch(r"^[0-9a-fA-F]{64}$", expected_sha):
            overall_status = "INVALID"
            file_results.append({"path": rel_path_str, "status": "INVALID_PATH"})
            continue

        # Optional bytes kontrolü: Alan mevcut ve null ise (veya bool, negatif, string ise) geçersizdir.
        if has_bytes_key and expected_bytes is None:
            overall_status = "INVALID"
            file_results.append({"path": rel_path_str, "status": "INVALID_PATH"})
            continue

        if expected_bytes is not None:
            if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int) or expected_bytes < 0:
                overall_status = "INVALID"
                file_results.append({"path": rel_path_str, "status": "INVALID_PATH"})
                continue

        # Güvenli dosya çözme (Root dışına çıkışları engelle)
        try:
            target_file = (root_path / rel_path_str).resolve()
            if not target_file.is_relative_to(root_path):
                overall_status = "INVALID"
                file_results.append({"path": rel_path_str, "status": "INVALID_PATH"})
                continue
        except Exception:
            overall_status = "INVALID"
            file_results.append({"path": rel_path_str, "status": "INVALID_PATH"})
            continue

        # Dosya varlık ve okunabilirlik kontrolü
        if not target_file.is_file():
            if overall_status != "INVALID":
                overall_status = "FAILED"
            file_results.append({"path": rel_path_str, "status": "MISSING"})
            continue

        try:
            file_size = target_file.stat().st_size
        except Exception:
            if overall_status != "INVALID":
                overall_status = "FAILED"
            file_results.append({"path": rel_path_str, "status": "ERROR"})
            continue

        # Boyut kontrolü
        if expected_bytes is not None and file_size != expected_bytes:
            if overall_status != "INVALID":
                overall_status = "FAILED"
            file_results.append({"path": rel_path_str, "status": "SIZE_MISMATCH"})
            continue

        # SHA256 hash hesaplama (streaming / chunk ile bellek dostu)
        try:
            actual_sha = compute_sha256(target_file)
        except Exception:
            if overall_status != "INVALID":
                overall_status = "FAILED"
            file_results.append({"path": rel_path_str, "status": "ERROR"})
            continue

        if actual_sha != expected_sha.lower():
            if overall_status != "INVALID":
                overall_status = "FAILED"
            file_results.append({"path": rel_path_str, "status": "MISMATCH"})
            continue

        file_results.append({"path": rel_path_str, "status": "OK"})
        ok_count += 1

    # Genel statü belirleme
    if overall_status == "INVALID":
        report["status"] = "INVALID"
        report["message"] = get_translation(lang, "invalid_manifest")
        exit_code = 2
    elif ok_count == total_files and total_files > 0:
        report["status"] = "OK"
        report["message"] = get_translation(lang, "all_verified")
        exit_code = 0
    else:
        report["status"] = "FAILED"
        report["message"] = get_translation(lang, "some_failed")
        exit_code = 1

    report["summary"] = {"total": total_files, "ok": ok_count}
    report["files"] = file_results

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        # --json yoksa insan için sade Türkçe sonuç ve dosya listesi yazdır
        labels = {"OK": "Doğrulandı", "FAILED": "Sorun bulundu", "INVALID": "Geçersiz", "MISMATCH": "Değişmiş", "MISSING": "Eksik", "SIZE_MISMATCH": "Boyutu farklı", "INVALID_PATH": "Geçersiz yol veya veri", "ERROR": "Okunamadı"} if lang == "tr" else {}
        print(get_translation(lang, "cli_summary", status=labels.get(report["status"], report["status"]), total=total_files, ok=ok_count))
        print(report["message"])
        for f_res in file_results:
            print(get_translation(lang, "file_line", path=f_res["path"], status=labels.get(f_res["status"], f_res["status"])))

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
