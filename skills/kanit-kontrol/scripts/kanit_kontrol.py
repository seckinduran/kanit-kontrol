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
            "invalid_cli": "Geçersiz komut. Manifest dosyasını ve --root klasörünü belirtin; yardım için --help kullanın.",
            "cli_description": "Kanıt Kontrol - SHA256 Bütünlük Denetleyicisi",
            "manifest_help": "Manifest JSON dosya yolu",
            "root_help": "Kök dizin",
            "json_help": "Yalnız JSON çıktı üret",
            "language_help": "Dil seçimi (tr|en)",
            "all_verified": "Tüm dosyalar başarıyla doğrulandı.",
            "some_failed": "Bazı dosyalarda bütünlük uyumsuzluğu veya eksiklik tespit edildi.",
            "invalid_manifest": "Geçersiz manifest dosyası, eksik veya hatalı yapı.",
            "cli_summary": "Kanıt Kontrol Sonucu: {status} | Toplam: {total}, Başarılı: {ok}",
            "file_line": "  - {path}: {status}",
        },
        "en": {
            "invalid_cli": "Invalid command. Provide a manifest and --root folder; use --help for usage.",
            "cli_description": "Evidence Check - SHA256 Integrity Verifier",
            "manifest_help": "Manifest JSON file path",
            "root_help": "Root folder",
            "json_help": "Produce JSON output only",
            "language_help": "Output language (tr|en)",
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


def requested_cli_options(argv):
    options = argv[:argv.index("--")] if "--" in argv else argv
    lang = "tr"
    for index, value in enumerate(options):
        choice = options[index + 1] if value == "--lang" and index + 1 < len(options) else (value.split("=", 1)[1] if value.startswith("--lang=") else None)
        if choice in ("tr", "en"):
            lang = choice
    return lang, "--json" in options


def report_cli_error(lang, json_output):
    report = {
        "status": "INVALID",
        "message": get_translation(lang, "invalid_cli"),
        "summary": {"total": 0, "ok": 0},
        "files": []
    }
    print(json.dumps(report, ensure_ascii=False) if json_output else report["message"])
    sys.exit(2)


class CliArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Tüm ayrıştırma hataları aynı, dil seçimini koruyan rapor yoluna gider.
        raise SystemExit(2)


def main():
    configure_utf8_stdout()
    cli_lang, cli_json = requested_cli_options(sys.argv[1:])
    parser = CliArgumentParser(description=get_translation(cli_lang, "cli_description"))
    parser.add_argument("manifest", type=str, nargs="?", help=get_translation(cli_lang, "manifest_help"))
    parser.add_argument("--root", type=str, help=get_translation(cli_lang, "root_help"))
    parser.add_argument("--json", action="store_true", help=get_translation(cli_lang, "json_help"))
    parser.add_argument("--lang", type=str, default="tr", choices=["tr", "en"], help=get_translation(cli_lang, "language_help"))

    try:
        args = parser.parse_args()
    except SystemExit as exc:
        if exc.code == 0:
            sys.exit(0)
        report_cli_error(cli_lang, cli_json)

    if not args.manifest or not args.root:
        report_cli_error(args.lang, args.json)

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
    seen_resolved_paths = set()
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

        # Eşdeğer yol yazımları aynı dosyayı ikinci kez doğrulamasın.
        if target_file in seen_resolved_paths:
            overall_status = "INVALID"
            file_results.append({"path": rel_path_str, "status": "INVALID_PATH"})
            continue
        seen_resolved_paths.add(target_file)

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
