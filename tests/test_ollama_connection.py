import os
import unittest
from unittest.mock import Mock, patch

import ai.engine as engine


class OllamaConnectionTests(unittest.TestCase):
    def test_health_check_reports_running(self):
        response = Mock(status_code=200)
        session = Mock()
        session.get.return_value = response

        with patch("ai.engine.get_ollama_session", return_value=session):
            self.assertTrue(engine.check_ollama_health())

        self.assertTrue(engine._ollama_status["running"])

    def test_health_check_records_connection_error(self):
        session = Mock()
        session.get.side_effect = OSError("connection refused")

        with patch("ai.engine.get_ollama_session", return_value=session):
            self.assertFalse(engine.check_ollama_health())

        self.assertFalse(engine._ollama_status["running"])
        self.assertIn("connection refused", engine._ollama_status["error"])

    def test_generate_stream_uses_selected_model_without_live_ollama(self):
        with patch("ai.engine.load_settings", return_value={"personality": "jarvis"}), patch(
            "ai.engine.select_model", return_value="llama3"
        ), patch(
            "ai.engine.raw_stream_with_fallback", return_value=iter(["Ahoj"])
        ):
            reply = "".join(engine.generate_stream("UZIVATEL:\nahoj", chat_model="auto"))

        self.assertEqual(reply, "Ahoj")
        self.assertEqual(engine._ollama_status["active_model"], "llama3")


@unittest.skipUnless(os.getenv("JARVIS_RUN_INTEGRATION_TESTS") == "1", "Set JARVIS_RUN_INTEGRATION_TESTS=1 to test live Ollama.")
class LiveOllamaIntegrationTests(unittest.TestCase):
    def test_live_ollama_stream(self):
        self.assertTrue(engine.check_ollama_health())
        chunks = list(engine.generate_stream("Napiš jednu krátkou větu česky.", chat_model="llama3"))
        self.assertTrue("".join(chunks).strip())


if __name__ == "__main__":
    unittest.main()
