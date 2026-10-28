import unittest
from app.web_api import AppBridge
from app.history import ActionHistoryManager
from app.ai_assistant import AIAssistant


class TestV2NewFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge = AppBridge()

    def test_01_system_health(self):
        health = self.bridge.get_system_health()
        self.assertTrue(health.get("success"))
        self.assertIn("cpu_percent", health)
        self.assertIn("ram_percent", health)
        self.assertIn("disk_c", health)
        self.assertIn(health.get("status"), ["great", "warning", "critical"])
        self.assertGreaterEqual(health["cpu_percent"], 0)
        self.assertLessEqual(health["cpu_percent"], 100)
        self.assertGreaterEqual(health["ram_percent"], 0)
        self.assertLessEqual(health["ram_percent"], 100)

    def test_02_action_history(self):
        hist_mgr = ActionHistoryManager()
        hist_mgr.clear()
        act_id = hist_mgr.record_action(
            action_type="tweak_apply",
            title="Тестовый твик",
            title_en="Test tweak",
            revert_data={"tweak_id": "test", "action": "revert"},
            can_undo=True
        )
        self.assertTrue(act_id.startswith("act_"))
        items = hist_mgr.get_history()
        self.assertGreaterEqual(len(items), 1)
        self.assertEqual(items[0]["id"], act_id)
        self.assertFalse(items[0]["undone"])

        # Mark undone
        success = hist_mgr.mark_undone(act_id)
        self.assertTrue(success)
        items_after = hist_mgr.get_history()
        self.assertTrue(items_after[0]["undone"])
        hist_mgr.clear()

    def test_03_app_changelog(self):
        # 7-Zip or Telegram
        res = self.bridge.get_app_changelog("7zip")
        self.assertTrue(res.get("success"))
        self.assertIn("app_name", res)
        self.assertIn("notes", res)

    def test_04_network_ip_info(self):
        res = self.bridge.get_network_ip_info()
        self.assertTrue(res.get("success"))
        self.assertIn("ip", res)
        self.assertIn("country", res)
        self.assertIn("flag", res)

    def test_05_winget_search(self):
        res = self.bridge.search_winget_packages("vlc")
        self.assertTrue(res.get("success"))
        self.assertIn("results", res)
        self.assertGreaterEqual(len(res["results"]), 1)

    def test_06_ai_assistant_offline(self):
        res = self.bridge.ask_ai_assistant("как ускорить игры и уменьшить пинг?")
        self.assertTrue(res.get("success"))
        self.assertIn("answer", res)
        self.assertTrue(len(res["answer"]) > 20)

    def test_07_ai_assistant_ollama_config(self):
        # Test configuring Ollama zero-auth provider
        saved = self.bridge.save_ai_config("ollama", "", "llama3.2")
        self.assertTrue(saved.get("success"))
        cfg = self.bridge.get_ai_config()
        self.assertEqual(cfg.get("provider"), "ollama")
        self.assertTrue(cfg.get("has_key"))
        self.assertEqual(cfg.get("model"), "llama3.2")

        # When asking, if local ollama is not running, falls back gracefully to offline DB with note
        res = self.bridge.ask_ai_assistant("как отключить телеметрию?")
        self.assertTrue(res.get("success"))
        self.assertIn("answer", res)

        # Restore default
        self.bridge.save_ai_config("gemini", "", "gemini-1.5-flash")


if __name__ == "__main__":
    unittest.main()
