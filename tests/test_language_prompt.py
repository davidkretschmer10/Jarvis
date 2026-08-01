import unittest

from ai.engine import _language_instruction, _system_prompt
from ai.prompts.master_prompt import build_user_task_prompt


class LanguagePromptTests(unittest.TestCase):
    def test_system_prompt_prefers_czech(self):
        prompt = _system_prompt()
        self.assertIn("Mluv česky pokud uživatel píše česky.", prompt)

    def test_language_instruction_is_added_for_czech(self):
        instruction = _language_instruction("udelej mi test prosim")
        self.assertIn("Odpovez v jazyce posledni zpravy uzivatele", instruction)
        self.assertIn("pokud je jazyk nejasny, odpovez cesky", instruction)

    def test_language_instruction_allows_switching_language(self):
        instruction = _language_instruction("Can you explain what you can do?")
        self.assertIn("prepni odpoved do tohoto jazyka", instruction)
        self.assertIn("Can you explain what you can do?", instruction)

    def test_user_task_prompt_includes_latest_message_for_language_detection(self):
        prompt = build_user_task_prompt(
            user_text="Was kannst du machen?",
            history=["Ty: ahoj", "Jarvis: Ahoj."],
        )
        self.assertIn("POSLEDNI ZPRAVA UZIVATELE", prompt)
        self.assertIn("Was kannst du machen?", prompt)


if __name__ == "__main__":
    unittest.main()
