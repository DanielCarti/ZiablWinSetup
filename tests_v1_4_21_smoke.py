"""
Comprehensive Smoke Test Suite for ZiablWinSetup v1.4.21.
Tests all modified and newly created modules:
- app.virustotal
- app.tweaks
- app.registry_cleaner
- app.catalog
- app.detector
- app.web_api
- app.utils
- app.i18n
- app.backup_restore
- app.version
"""

import sys
import os
import unittest
from pathlib import Path
import tempfile

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath("."))


class TestVersion(unittest.TestCase):
    def test_version_string(self):
        from app.version import __version__, APP_NAME
        self.assertEqual(__version__, "1.4.23")
        self.assertEqual(APP_NAME, "ZiablWinSetup")


class TestUtils(unittest.TestCase):
    def test_get_user_documents_dir(self):
        from app.utils import get_user_documents_dir
        doc_dir = get_user_documents_dir()
        self.assertIsInstance(doc_dir, Path)
        self.assertTrue(doc_dir.exists(), f"Path does not exist: {doc_dir}")
        self.assertTrue(doc_dir.is_dir())


class TestVirusTotal(unittest.TestCase):
    def test_format_file_size(self):
        from app.virustotal import format_file_size
        self.assertEqual(format_file_size(500), "500 Б")
        self.assertEqual(format_file_size(1024), "1.0 КБ")
        self.assertEqual(format_file_size(1024 * 1024 * 5), "5.0 МБ")
        self.assertEqual(format_file_size(1024 * 1024 * 1024 * 2), "2.00 ГБ")

    def test_calculate_file_sha256(self):
        from app.virustotal import calculate_file_sha256
        with tempfile.NamedTemporaryFile("wb", delete=False) as f:
            f.write(b"Hello VirusTotal!")
            temp_path = f.name

        try:
            h, sz = calculate_file_sha256(temp_path)
            self.assertEqual(sz, 17)
            import hashlib
            expected = hashlib.sha256(b"Hello VirusTotal!").hexdigest().lower()
            self.assertEqual(h, expected)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_multipart_payload(self):
        from app.virustotal import _build_multipart_payload
        fields = {"test_field": "test_val"}
        files = {"file": ("test.txt", b"abc")}
        body, ctype = _build_multipart_payload(fields, files)
        self.assertTrue(ctype.startswith("multipart/form-data; boundary="))
        self.assertIn(b"test_field", body)
        self.assertIn(b"test_val", body)
        self.assertIn(b"test.txt", body)
        self.assertIn(b"abc", body)

    def test_parse_vt_file_response(self):
        from app.virustotal import _parse_vt_file_response
        fake_data = {
            "data": {
                "attributes": {
                    "last_analysis_stats": {
                        "malicious": 2,
                        "suspicious": 1,
                        "undetected": 65,
                        "harmless": 2,
                    },
                    "last_analysis_results": {
                        "Avast": {"category": "undetected", "result": None},
                        "Kaspersky": {"category": "malicious", "result": "Trojan.Win32.Generic"},
                        "Defender": {"category": "suspicious", "result": "PUA:Win32/Test"},
                    },
                    "last_analysis_date": 1700000000,
                    "reputation": -5,
                    "type_description": "PE32 Executable",
                }
            }
        }
        res = _parse_vt_file_response(fake_data, "fake_sha256", "test.exe", 1024)
        self.assertTrue(res["success"])
        self.assertTrue(res["found"])
        self.assertEqual(res["verdict"], "malicious")
        self.assertEqual(res["malicious_count"], 2)
        self.assertEqual(res["suspicious_count"], 1)
        self.assertEqual(res["total_scanners"], 70)
        self.assertEqual(res["score_text"], "2 / 70")
        self.assertEqual(len(res["engines"]), 3)
        # Kaspersky should be first since malicious engines are prioritized
        self.assertEqual(res["engines"][0]["name"], "Kaspersky")
        self.assertEqual(res["engines"][0]["category"], "malicious")
        self.assertEqual(res["engines"][1]["name"], "Defender")
        self.assertEqual(res["engines"][1]["category"], "suspicious")

    def test_scan_file_missing(self):
        from app.virustotal import scan_file_by_path
        res = scan_file_by_path("C:\\non_existent_file_path_12345.xyz")
        self.assertFalse(res["success"])
        self.assertEqual(res["error_type"], "file_not_found")


    def test_validate_api_key(self):
        from app.virustotal import validate_virustotal_api_key
        # Test empty
        ok, msg = validate_virustotal_api_key("")
        self.assertFalse(ok)
        self.assertIn("пустым", msg)

        # Test vulgar / invalid format string ("хуй")
        ok, msg = validate_virustotal_api_key("хуй")
        self.assertFalse(ok)
        self.assertIn("64", msg)

        # Test too short
        ok, msg = validate_virustotal_api_key("abc123")
        self.assertFalse(ok)
        self.assertIn("64", msg)

        # Test non-hex characters
        ok, msg = validate_virustotal_api_key("z" * 64)
        self.assertFalse(ok)
        self.assertIn("64", msg)

    def test_settings_api_key(self):
        from app.settings import get_virustotal_api_key, set_virustotal_api_key
        orig_key = get_virustotal_api_key()
        try:
            self.assertTrue(set_virustotal_api_key("test_api_key_12345"))
            self.assertEqual(get_virustotal_api_key(), "test_api_key_12345")
        finally:
            set_virustotal_api_key(orig_key)


class TestCatalogAndDetector(unittest.TestCase):
    def test_new_apps_in_catalog(self):
        from app.catalog import get_catalog
        catalog = get_catalog()
        app_ids = [app.id for app in catalog]
        self.assertIn("rufus", app_ids)
        self.assertIn("hydralauncher", app_ids)

        rufus = next(a for a in catalog if a.id == "rufus")
        self.assertEqual(rufus.name, "Rufus")
        self.assertEqual(rufus.category, "utilities")
        self.assertTrue(rufus.direct_url.endswith(".exe"))
        self.assertTrue(rufus.notes)
        self.assertTrue(rufus.notes_en)

        hydra = next(a for a in catalog if a.id == "hydralauncher")
        self.assertEqual(hydra.name, "Hydra Launcher")
        self.assertEqual(hydra.category, "gaming")
        self.assertTrue(hydra.direct_url.endswith(".exe"))
        self.assertIn("/S", hydra.silent_args)
        self.assertTrue(hydra.notes)
        self.assertTrue(hydra.notes_en)

    def test_no_duplicate_app_ids(self):
        from app.catalog import get_catalog
        catalog = get_catalog()
        ids = [a.id for a in catalog]
        self.assertEqual(len(ids), len(set(ids)), f"Duplicate IDs in catalog: {[x for x in ids if ids.count(x) > 1]}")

    def test_detector_rules(self):
        from app.detector import DETECTION_RULES
        self.assertIn("rufus", DETECTION_RULES)
        self.assertIn("hydralauncher", DETECTION_RULES)
        self.assertTrue(len(DETECTION_RULES["rufus"]["patterns"]) > 0)
        self.assertTrue(len(DETECTION_RULES["hydralauncher"]["patterns"]) > 0)


class TestTweaks(unittest.TestCase):
    def test_tweaks_registry(self):
        from app.tweaks import TWEAKS, get_all_tweaks
        tweak_ids = [t.id for t in TWEAKS]
        self.assertIn("repair_system_files", tweak_ids)
        self.assertIn("restore_health_dism", tweak_ids)

        sfc = next(t for t in TWEAKS if t.id == "repair_system_files")
        self.assertEqual(sfc.type, "action")
        self.assertTrue(callable(sfc.apply))
        self.assertEqual(sfc.action_text, "Запустить сканирование")
        self.assertEqual(sfc.action_text_en, "Start Scan")

        dism = next(t for t in TWEAKS if t.id == "restore_health_dism")
        self.assertEqual(dism.type, "action")
        self.assertTrue(callable(dism.apply))
        self.assertEqual(dism.action_text, "Восстановить образ")
        self.assertEqual(dism.action_text_en, "Restore Health")

    def test_tweaks_serialization(self):
        from app.tweaks import TWEAKS
        for t in TWEAKS:
            d_ru = t.to_dict(lang="ru")
            d_en = t.to_dict(lang="en")
            self.assertIn("id", d_ru)
            self.assertIn("name", d_ru)
            self.assertIn("category", d_ru)
            self.assertIn("action_text", d_ru)
            self.assertIn("action_text", d_en)
            if t.id == "repair_system_files":
                self.assertEqual(d_ru["action_text"], "Запустить сканирование")
                self.assertEqual(d_en["action_text"], "Start Scan")


class TestRegistryCleaner(unittest.TestCase):
    def test_backups_dir(self):
        from app.registry_cleaner import get_backups_dir
        b_dir = get_backups_dir()
        self.assertIsInstance(b_dir, Path)
        self.assertTrue(b_dir.exists())

    def test_restore_registry_backup_invalid(self):
        from app.registry_cleaner import restore_registry_backup
        # Test non-existent file
        ok, msg = restore_registry_backup("C:\\non_existent_file.reg")
        self.assertFalse(ok)
        self.assertIn("не найден", msg)

        # Test non-.reg file
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("not a reg file")
            tname = f.name
        try:
            ok, msg = restore_registry_backup(tname)
            self.assertFalse(ok)
            self.assertIn(".reg", msg)
        finally:
            if os.path.exists(tname):
                os.remove(tname)


class TestBackupRestore(unittest.TestCase):
    def test_default_backup_dir(self):
        from app.backup_restore import get_default_backup_dir
        b_dir = get_default_backup_dir()
        self.assertIsInstance(b_dir, Path)
        self.assertTrue(b_dir.exists())

    def test_import_apps_backup_txt(self):
        from app.backup_restore import import_apps_backup
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("=== РЕЗЕРВНАЯ КОПИЯ ПРИЛОЖЕНИЙ ZIABLWINSETUP ===\n")
            f.write("Дата: 14.10.2026 12:00:00\n")
            f.write("Компьютер: Test-PC\n\n")
            f.write("=== ПРОГРАММЫ ИЗ КАТАЛОГА (1) ===\n")
            f.write("• Rufus (4.15) [utilities]\n\n")
            f.write("=== ДРУГИЕ ПРОГРАММЫ СИСТЕМЫ (1) ===\n")
            f.write("• TestApp (1.0)\n")
            tname = f.name
        try:
            res = import_apps_backup(tname)
            self.assertTrue(res.get("success"))
            self.assertEqual(len(res.get("catalog_apps", [])), 1)
            self.assertEqual(res["catalog_apps"][0]["name"], "Rufus")
            self.assertEqual(len(res.get("system_apps", [])), 1)
            self.assertEqual(res["system_apps"][0]["name"], "TestApp")
        finally:
            if os.path.exists(tname):
                os.remove(tname)



class TestI18n(unittest.TestCase):
    def test_i18n_keys_parity(self):
        from app.i18n import STRINGS
        ru_keys = set(STRINGS["ru"].keys())
        en_keys = set(STRINGS["en"].keys())

        # Check required v1.4.21 keys
        v1421_keys = [
            "reg_btn_backups_folder",
            "reg_btn_restore_backup",
            "tab_virustotal",
            "vt_title",
            "vt_subtitle",
            "vt_api_key_title",
            "vt_api_key_desc",
            "vt_save_key_btn",
            "vt_change_key_btn",
            "vt_drop_title",
            "vt_drop_subtitle",
            "vt_btn_choose",
            "vt_clean_verdict",
            "vt_malicious_verdict",
            "vt_suspicious_verdict",
            "vt_open_online",
            "vt_filter_all",
            "vt_filter_malicious",
            "vt_btn_upload",
            "vt_upload_hint",
        ]
        for k in v1421_keys:
            self.assertIn(k, ru_keys, f"Missing {k} in RU")
            self.assertIn(k, en_keys, f"Missing {k} in EN")


class TestWebAPI(unittest.TestCase):
    def test_app_bridge_instantiation_and_methods(self):
        from app.web_api import AppBridge
        bridge = AppBridge()

        # Check basic methods return valid structures
        init_data = bridge.get_initial_data()
        self.assertEqual(init_data["system_info"]["app_version"], "1.4.23")

        cat = init_data["apps"]
        self.assertIsInstance(cat, list)
        self.assertTrue(len(cat) > 50)

        tweaks = bridge.get_tweaks()
        self.assertIsInstance(tweaks, list)
        self.assertEqual(len(tweaks), 14)

        # VirusTotal bridge methods
        vt_cfg = bridge.get_virustotal_config()
        self.assertIn("has_key", vt_cfg)
        self.assertIn("masked_key", vt_cfg)

        scan_res = bridge.scan_virustotal_path("C:\\non_existent_path.exe")
        self.assertFalse(scan_res.get("success"))

        # Test save_virustotal_api_key with invalid input
        res_invalid = bridge.save_virustotal_api_key("хуй")
        self.assertFalse(res_invalid.get("success"))
        self.assertIn("64", res_invalid.get("message", ""))

        # Test save_virustotal_api_key with empty string (clear)
        res_empty = bridge.save_virustotal_api_key("")
        self.assertTrue(res_empty.get("success"))
        self.assertFalse(res_empty.get("has_key"))

        # Test backups dir opening
        b_res = bridge.open_backups_directory()
        self.assertTrue(b_res.get("success"))
        self.assertTrue(os.path.isdir(b_res.get("path")))

        # Test scan_virustotal_hash with invalid hash
        h_res = bridge.scan_virustotal_hash("invalid_hash", "test.exe", 100)
        self.assertFalse(h_res.get("success"))
        self.assertEqual(h_res.get("error_type"), "invalid_hash")

        # Test restore_registry_from_text
        from unittest.mock import patch
        with patch("app.registry_cleaner.restore_registry_backup", return_value=(True, "OK")):
            r_res = bridge.restore_registry_from_text("Windows Registry Editor Version 5.00\n", "test.reg")
            self.assertTrue(r_res.get("success"))

        # Test get_tweak_running_status
        t_res = bridge.get_tweak_running_status("repair_system_files")
        self.assertIn("running", t_res)
        self.assertIn("completed", t_res)


class TestTweakProcessHandling(unittest.TestCase):
    def test_handle_tracking(self):
        from app.tweaks import get_tweak_process_handle, set_tweak_process_handle
        set_tweak_process_handle("test_tweak", 9999)
        self.assertEqual(get_tweak_process_handle("test_tweak"), 9999)
        set_tweak_process_handle("test_tweak", None)
        self.assertIsNone(get_tweak_process_handle("test_tweak"))

    def test_batch_file_no_bom(self):
        import tempfile
        from unittest.mock import patch
        from app.tweaks import _launch_elevated_bat
        with patch("ctypes.windll.shell32.ShellExecuteExW", return_value=1):
            ok = _launch_elevated_bat("test_nobom", "@echo off\necho hello\n")
            self.assertTrue(ok)
            bat_path = Path(tempfile.gettempdir()) / "ziabl_test_nobom.bat"
            self.assertTrue(bat_path.exists())
            raw_bytes = bat_path.read_bytes()
            # Must NOT start with UTF-8 BOM (\xef\xbb\xbf)
            self.assertFalse(raw_bytes.startswith(b"\xef\xbb\xbf"), "Batch file must not contain UTF-8 BOM!")
            self.assertTrue(raw_bytes.startswith(b"@echo off"))

    def test_tweak_english_messages(self):
        from app.tweaks import apply_tweak_by_id
        res_en = apply_tweak_by_id("clean_winsetup_installers", lang="en")
        self.assertTrue(res_en.get("success"))
        # Message must be in English
        self.assertIn("Installer cache", res_en.get("message", ""))
        self.assertIn("Installer cache", res_en.get("message_en", ""))

    def test_log_selection_and_copy_html(self):
        html_path = Path("app/ui/index.html")
        content = html_path.read_text(encoding="utf-8")
        self.assertIn("user-select: text !important;", content)
        self.assertIn("id=\"btnCopyLog\"", content)
        self.assertIn("copyFullLog", content)

    def test_registry_restore_utf16_and_cp866(self):
        from app.web_api import AppBridge
        bridge = AppBridge()
        from unittest.mock import patch
        saved_file_bytes = []
        def mock_restore(p):
            saved_file_bytes.append(Path(p).read_bytes())
            return True, "Restored"
        with patch("app.registry_cleaner.restore_registry_backup", side_effect=mock_restore):
            res = bridge.restore_registry_from_text("; test comment\n", "backup.reg")
            self.assertTrue(res.get("success"))
            self.assertEqual(len(saved_file_bytes), 1)
            # UTF-16 LE file must start with BOM FF FE
            self.assertTrue(saved_file_bytes[0].startswith(b"\xff\xfe"), "Registry file must be saved in UTF-16 LE with BOM")


if __name__ == "__main__":
    unittest.main()
