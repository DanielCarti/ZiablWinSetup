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
        self.assertEqual(__version__, "2.0.0")
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

    def test_item_exists_helper(self):
        import winreg
        from app.registry_cleaner import _item_exists, _delete_key_recursively
        test_sub = r"Software\ZiablTestItemExistsKey"
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, test_sub)
        winreg.SetValueEx(k, "TestVal", 0, winreg.REG_SZ, "Val1")
        winreg.CloseKey(k)

        self.assertTrue(_item_exists(winreg.HKEY_CURRENT_USER, test_sub))
        self.assertTrue(_item_exists(winreg.HKEY_CURRENT_USER, test_sub, "TestVal"))
        self.assertFalse(_item_exists(winreg.HKEY_CURRENT_USER, test_sub, "NoSuchVal"))
        self.assertFalse(_item_exists(winreg.HKEY_CURRENT_USER, r"Software\NoSuchKeyPathDoesNotExist"))

        # Clean up
        _delete_key_recursively(winreg.HKEY_CURRENT_USER, test_sub)
        self.assertFalse(_item_exists(winreg.HKEY_CURRENT_USER, test_sub))

    def test_clean_registry_issues_empty(self):
        from app.registry_cleaner import clean_registry_issues
        res = clean_registry_issues([])
        self.assertFalse(res["success"])
        self.assertEqual(res["cleaned_count"], 0)
        self.assertEqual(res["cleaned_ids"], [])

    def test_clean_registry_issues_hkcu_live(self):
        import winreg
        from app.registry_cleaner import clean_registry_issues, _item_exists
        test_sub = r"Software\ZiablTestCleanLiveKey"
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, test_sub)
        winreg.SetValueEx(k, "Sample", 0, winreg.REG_SZ, "123")
        winreg.CloseKey(k)

        issue = {
            "id": "reg_test_hkcu",
            "category": "uninstall",
            "category_title": "Test Category",
            "title": "Test Title",
            "detail": "Test Detail",
            "root_key": "HKEY_CURRENT_USER",
            "hkey_val": winreg.HKEY_CURRENT_USER,
            "subkey_path": test_sub,
            "value_name": None,
            "action_type": "delete_key",
            "checked": True,
        }

        res = clean_registry_issues([issue])
        self.assertTrue(res["success"])
        self.assertEqual(res["cleaned_count"], 1)
        self.assertEqual(res["errors_count"], 0)
        self.assertEqual(res["cleaned_ids"], ["reg_test_hkcu"])
        self.assertFalse(_item_exists(winreg.HKEY_CURRENT_USER, test_sub))
        self.assertTrue(os.path.isfile(res["backup_path"]))

        # Verify backup file starts with UTF-16 LE BOM
        with open(res["backup_path"], "rb") as bf:
            bom = bf.read(2)
            self.assertEqual(bom, b"\xff\xfe", "Backup must be UTF-16 LE with BOM")
        # Cleanup backup file
        try:
            os.remove(res["backup_path"])
        except Exception:
            pass

    def test_clean_registry_issues_uac_declined(self):
        import winreg
        from unittest.mock import patch
        from app.registry_cleaner import clean_registry_issues

        issue = {
            "id": "reg_test_hklm",
            "category": "app_paths",
            "category_title": "Test Category",
            "title": "Test HKLM App",
            "detail": "Missing file",
            "root_key": "HKEY_LOCAL_MACHINE",
            "hkey_val": winreg.HKEY_LOCAL_MACHINE,
            "subkey_path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\devenv.exe",
            "value_name": None,
            "action_type": "delete_key",
            "checked": True,
        }

        with patch("app.registry_cleaner._delete_issues_elevated", side_effect=PermissionError("UAC_CANCELLED")):
            with patch("app.registry_cleaner._item_exists", return_value=True):
                with patch("app.utils.is_admin", return_value=False):
                    res = clean_registry_issues([issue])
                    self.assertFalse(res["success"])
                    self.assertEqual(res["cleaned_count"], 0)
                    self.assertEqual(res["errors_count"], 1)
                    self.assertEqual(res["cleaned_ids"], [])
                    self.assertIn("UAC", res["message"])
                    if os.path.isfile(res["backup_path"]):
                        try:
                            os.remove(res["backup_path"])
                        except Exception:
                            pass

    def test_clean_registry_issues_elevated_success(self):
        import winreg
        from unittest.mock import patch
        from app.registry_cleaner import clean_registry_issues

        issue = {
            "id": "reg_test_elevated_sim",
            "category": "app_paths",
            "category_title": "Test Category",
            "title": "Test Elevated Sim",
            "detail": "Test detail",
            "root_key": "HKEY_LOCAL_MACHINE",
            "hkey_val": winreg.HKEY_LOCAL_MACHINE,
            "subkey_path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\devenv.exe",
            "value_name": None,
            "action_type": "delete_key",
            "checked": True,
        }

        deleted_items = set()

        def mock_elevated_delete(issues):
            for i in issues:
                deleted_items.add(i["id"])

        def mock_item_exists(hkey, sub, vname=None):
            # If deleted via elevated mock, report False
            if issue["id"] in deleted_items:
                return False
            return True

        with patch("app.utils.is_admin", return_value=False):
            with patch("app.registry_cleaner._item_exists", side_effect=mock_item_exists):
                with patch("app.registry_cleaner._delete_issues_elevated", side_effect=mock_elevated_delete) as mock_elev:
                    res = clean_registry_issues([issue])
                    self.assertTrue(mock_elev.called)
                    self.assertTrue(res["success"])
                    self.assertEqual(res["cleaned_count"], 1)
                    self.assertEqual(res["errors_count"], 0)
                    self.assertEqual(res["cleaned_ids"], ["reg_test_elevated_sim"])
                    if os.path.isfile(res["backup_path"]):
                        try:
                            os.remove(res["backup_path"])
                        except Exception:
                            pass


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
        from app.version import __version__
        init_data = bridge.get_initial_data()
        self.assertEqual(init_data["system_info"]["app_version"], __version__)

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

        # Test clean_registry_selected popping only cleaned_ids
        bridge._last_registry_issues = {
            "reg_1": {"id": "reg_1", "title": "Item 1"},
            "reg_2": {"id": "reg_2", "title": "Item 2"}
        }
        with patch("app.web_api.clean_registry_issues", return_value={"success": True, "cleaned_count": 1, "errors_count": 1, "cleaned_ids": ["reg_1"], "message": "Partial"}):
            c_res = bridge.clean_registry_selected(["reg_1", "reg_2"])
            self.assertTrue(c_res["success"])
            self.assertNotIn("reg_1", bridge._last_registry_issues)
            self.assertIn("reg_2", bridge._last_registry_issues)


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

    def test_index_html_javascript_syntax(self):
        import re, subprocess, shutil
        node_bin = shutil.which("node")
        self.assertIsNotNone(node_bin, "Node.js must be installed for JS syntax validation")

        html_path = Path("app/ui/index.html")
        html = html_path.read_text(encoding="utf-8")
        scripts = re.findall(r"<script.*?>([\s\S]*?)</script>", html, re.IGNORECASE)
        valid_scripts = [s for s in scripts if len(s.strip()) > 50]
        self.assertGreater(len(valid_scripts), 0, "Must find at least one valid script block in index.html")

        import tempfile
        for idx, s in enumerate(valid_scripts):
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".js", delete=False) as tf:
                tf.write(s)
                t_name = tf.name
            try:
                res = subprocess.run([node_bin, "--check", t_name], capture_output=True, text=True)
                self.assertEqual(
                    res.returncode, 0,
                    f"JavaScript Syntax Error in script {idx} of app/ui/index.html:\n{res.stderr}"
                )
            finally:
                try:
                    os.unlink(t_name)
                except Exception:
                    pass

    def test_init_app_defaults_and_translations_safety(self):
        html_path = Path("app/ui/index.html")
        content = html_path.read_text(encoding="utf-8")
        self.assertIn("window.onerror", content, "Global error handler window.onerror must exist")
        self.assertIn("try { applyTranslations(); }", content, "applyTranslations call in initAppDefaults must be wrapped in try/catch")
        self.assertIn("try { renderCategories(); }", content, "renderCategories call in initAppDefaults must be wrapped in try/catch")
        self.assertIn("try { renderCards(); }", content, "renderCards call in initAppDefaults must be wrapped in try/catch")

    def test_english_localization_coverage(self):
        html_path = Path("app/ui/index.html")
        content = html_path.read_text(encoding="utf-8")

        # 1. Sidebar Tools localization in applyTranslations
        self.assertIn("updateQaLabel('qaRegistryCleaner'", content)
        self.assertIn("updateQaLabel('qaBackupExport'", content)
        self.assertIn("updateQaLabel('qaBackupRestore'", content)
        self.assertIn("secSystemTools", content)

        # 2. Updates Banner bilingual template
        self.assertIn("✨ Updates available for {count} applications", content)
        self.assertIn("syncUpdatesUi();", content)

        # 3. Startup Manager badges & counter pill
        self.assertIn("Total: ${totalCount} (Enabled: ${enabledCount})", content)
        self.assertIn("Windows Service", content)
        self.assertIn("Task Scheduler", content)
        self.assertIn("Startup Folder", content)
        self.assertIn("Store / UWP", content)

        # 4. VirusTotal status, card description, placeholder & labels
        self.assertIn("API key not configured", content)
        self.assertIn("Enter API key", content)
        self.assertIn("Paste your 64-character VirusTotal API key...", content)
        self.assertIn("lblVtFileName", content)
        self.assertIn("lblVtFileSize", content)
        self.assertIn("lblVtDate", content)
        self.assertIn("lblVtType", content)
        self.assertIn("btnCopyVtHash", content)

        # 5. Registry Cleaner modal elements
        self.assertIn("lblRegCleanerTitle", content)
        self.assertIn("lblRegCleanerSubtitle", content)
        self.assertIn("btnRegSelectAll", content)
        self.assertIn("btnRegDeselectAll", content)
        self.assertIn("btnRegClose", content)
        self.assertIn("chipRegAll", content)
        self.assertIn("chipRegUninst", content)
        self.assertIn("chipRegAuto", content)

    def test_v1_4_27_features(self):
        from app.settings import get_accent_color, set_accent_color
        from app.utils import open_winget_store
        from app.web_api import AppBridge

        # 1. Accent color persistence
        orig_accent = get_accent_color()
        try:
            self.assertEqual(set_accent_color("purple"), "purple")
            self.assertEqual(get_accent_color(), "purple")
            self.assertEqual(set_accent_color("invalid_color"), "blue")
        finally:
            set_accent_color(orig_accent)

        # 2. AppBridge restart_as_admin & set_accent_color presence
        self.assertTrue(hasattr(AppBridge, "restart_as_admin"))
        self.assertTrue(hasattr(AppBridge, "set_accent_color"))

        # 3. open_winget_store returns tuple with status and opened_via
        res_ok, opened_via = open_winget_store()
        self.assertTrue(res_ok)
        self.assertIn(opened_via, ("store_app", "browser"))

        # 4. Frontend UI elements for v1.4.27 in app/ui/index.html
        html_path = Path("app/ui/index.html")
        content = html_path.read_text(encoding="utf-8")

        # Accent colors in CSS & Settings
        self.assertIn('data-accent="purple"', content)
        self.assertIn('data-accent="green"', content)
        self.assertIn('data-accent="orange"', content)
        self.assertIn('data-accent="red"', content)
        self.assertIn('accent-swatches', content)
        self.assertIn('setAccentColor', content)

        # Admin status badge & 1-click elevation
        self.assertIn('id="adminStatusBadge"', content)
        self.assertIn('promptRestartAsAdmin', content)

        # Quick Presets in Apps catalog
        self.assertIn('id="presetsBar"', content)
        self.assertIn('presetEssential', content)
        self.assertIn('presetGaming', content)
        self.assertIn('presetOffice', content)
        self.assertIn('applyAppPreset', content)
        self.assertIn('APP_PRESETS', content)

        # Contextual search in header without forced apps redirection
        self.assertIn('filterTweaksList', content)
        self.assertIn("else if (currentMainTab === 'tweaks')", content)
        self.assertIn("else if (currentMainTab === 'metro')", content)

    def test_v1_4_28_features(self):
        from unittest.mock import patch
        """Проверка исправлений UAC перезапуска и плавающей панели для v1.4.28."""
        from app.version import __version__
        self.assertEqual(__version__, "2.0.0")

        # 1. request_admin_restart handles UAC cancellation and passes --restarted-from-pid
        from app.utils import request_admin_restart
        with patch("app.utils.is_admin", return_value=False):
            # When user clicks Cancel/No in UAC (ShellExecuteW returns <= 32)
            with patch("ctypes.windll.shell32.ShellExecuteW", return_value=5):
                ok, err = request_admin_restart()
                self.assertFalse(ok)
                self.assertIn("отклонен", err)

            # When user approves UAC (ShellExecuteW returns > 32)
            with patch("ctypes.windll.shell32.ShellExecuteW", return_value=42):
                with patch("app.single_instance.single_instance_guard.cleanup") as mock_cleanup:
                    ok, err = request_admin_restart()
                    self.assertTrue(ok)
                    self.assertEqual(err, "")
                    mock_cleanup.assert_called_once()

        # 2. single_instance_guard is_pid_alive helper
        from app.single_instance import is_pid_alive, get_other_app_processes
        self.assertTrue(is_pid_alive(os.getpid()))
        self.assertFalse(is_pid_alive(-9999))
        self.assertFalse(is_pid_alive(0))

        # Check get_other_app_processes with exclude_pids
        other = get_other_app_processes(exclude_pids={123456})
        self.assertIsInstance(other, list)

        # 3. Sticky Action Bar in app/ui/index.html
        html_path = Path("app/ui/index.html")
        content = html_path.read_text(encoding="utf-8")
        self.assertIn('id="stickyActionBar"', content)
        self.assertIn('sticky-action-bar', content)
        self.assertIn('btnStickyDownload', content)
        self.assertIn('btnStickyInstall', content)
        self.assertIn('updateStickyBar', content)
        self.assertIn('_hasStickyScrollListener', content)


    def test_v1_4_29_features(self):
        """Проверка всех 12 улучшений и исправлений v1.4.29."""
        from app.version import __version__
        self.assertEqual(__version__, "2.0.0")

        # 1. Official Rufus & Hydra Launcher icons
        self.assertTrue((Path("app/ui/icons/rufus.svg")).exists())
        self.assertTrue((Path("app/ui/icons/hydralauncher.svg")).exists())
        self.assertTrue((Path("app/ui/icons/rufus.png")).exists())
        self.assertTrue((Path("app/ui/icons/hydralauncher.png")).exists())

        # 2. VirusTotal Multiple Saved Keys API in settings.py
        from app.settings import (
            get_virustotal_keys, save_virustotal_key,
            delete_virustotal_key, set_active_virustotal_key
        )
        saved_keys = get_virustotal_keys()
        self.assertIsInstance(saved_keys, list)

        # 3. Startup Manager Impact calculation
        from app.startup_manager import _calculate_startup_impact
        item_heavy = {"name": "Discord", "command": "discord.exe", "file_path": "", "enabled": True}
        res_heavy = _calculate_startup_impact(item_heavy)
        self.assertEqual(res_heavy["impact"], "high")
        self.assertEqual(res_heavy["impact_en"], "High")

        item_light = {"name": "AudioTrayHelper", "command": "tray.exe", "file_path": "", "enabled": True}
        res_light = _calculate_startup_impact(item_light)
        self.assertEqual(res_light["impact"], "low")
        self.assertEqual(res_light["impact_en"], "Low")

        # 4. Tweaks shell notification without restarting explorer
        import app.tweaks as tweaks
        self.assertTrue(hasattr(tweaks, "_notify_shell_settings_changed"))
        # Check source code to ensure searchbox and file ext use notify_shell_settings_changed
        import inspect
        searchbox_code = inspect.getsource(tweaks._apply_taskbar_search_hidden)
        self.assertIn("_notify_shell_settings_changed", searchbox_code)
        self.assertNotIn("_restart_explorer", searchbox_code)

        file_ext_code = inspect.getsource(tweaks._apply_file_ext)
        self.assertIn("_notify_shell_settings_changed", file_ext_code)
        self.assertNotIn("_restart_explorer", file_ext_code)

        # 5. Backup driver & GUID filtering
        from app.backup_restore import _is_driver_or_component
        self.assertTrue(_is_driver_or_component("1527c705-728b-4a5f-98c3-c287b4618e7c"))
        self.assertTrue(_is_driver_or_component("AMD GPIO Controller"))
        self.assertTrue(_is_driver_or_component("AMD I2C Driver"))
        self.assertTrue(_is_driver_or_component("AMD Chipset Software"))
        self.assertFalse(_is_driver_or_component("Google Chrome"))
        self.assertFalse(_is_driver_or_component("Visual Studio Code"))

        # 6. Frontend checks in app/ui/index.html
        html = Path("app/ui/index.html").read_text(encoding="utf-8")
        # Tweaks view modes & local search
        self.assertIn("tweaksSearchInput", html)
        self.assertIn("btnTweakViewGrid", html)
        self.assertIn("btnTweakViewCompact", html)
        self.assertIn("btnTweakViewList", html)
        self.assertIn("setTweaksViewMode", html)
        self.assertIn("filterTweaksLocal", html)

        # Startup impact badges
        self.assertIn("startup-impact-badge", html)
        self.assertIn("impact-high", html)

        # VirusTotal saved keys modal
        self.assertIn("id=\"vtKeysModal\"", html)
        self.assertIn("btnSavedVtKeys", html)
        self.assertIn("openVtKeysModal", html)

        # Backup modal driver filter & localization
        self.assertIn("chkShowBackupDrivers", html)
        self.assertIn("toggleShowBackupDrivers", html)
        self.assertIn("lblBackupModalTitle", html)
        self.assertIn("lblBackupTabCatalogText", html)

        # GitHub URL fix (DanielCarti/ZiablWinSetup)
        self.assertIn("DanielCarti/ZiablWinSetup/issues/new", html)
        self.assertNotIn("DanielCarti/WinSetup/issues/new", html)

        # No competitor mentions
        self.assertNotIn("ccleaner", html.lower())



    def test_v2_0_0_milestone_features(self):
        """Проверка ключевых улучшений v2.0.0 (Загрузки, скорость/ETA, отмена, персистентность темы, бэкап отмена)."""
        from app.version import __version__
        self.assertEqual(__version__, "2.0.0")

        # 1. Downloader active responses and immediate cancel support
        from app.downloader import Downloader
        dl = Downloader()
        self.assertTrue(hasattr(dl, "_active_responses"))
        self.assertIsInstance(dl._active_responses, dict)

        # 2. Web API clean_downloaded_installers tuple unpacking safety
        from app.web_api import AppBridge
        bridge = AppBridge()
        clean_res = bridge.clean_downloaded_installers()
        self.assertIsInstance(clean_res, dict)
        self.assertIn("success", clean_res)
        self.assertIn("message", clean_res)

        # 3. Web API open_downloads_folder and open_app_download_folder methods
        self.assertTrue(hasattr(bridge, "open_downloads_folder"))
        self.assertTrue(hasattr(bridge, "open_app_download_folder"))

        # 4. Web API export_apps_backup_dialog cancel handling (returns cancelled: True when no path chosen)
        dlg_res = bridge.export_apps_backup_dialog()
        self.assertIsInstance(dlg_res, dict)

        # 5. Frontend UI checks for Downloads manager, live badge, and accent persistence
        html = Path("app/ui/index.html").read_text(encoding="utf-8")
        self.assertIn("tabBtnDownloads", html)
        self.assertIn("tabDownloadsBadge", html)
        self.assertIn("viewDownloads", html)
        self.assertIn("dlListContainer", html)
        self.assertIn("openDownloadsFolder", html)
        self.assertIn("clearCompletedDownloads", html)
        self.assertIn("ziabl_accent_color", html)
        self.assertIn("appData.settings = data.settings", html)

        # No competitor mentions
        self.assertNotIn("ccleaner", html.lower())


if __name__ == "__main__":
    unittest.main()
