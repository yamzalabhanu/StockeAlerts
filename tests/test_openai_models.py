import unittest

from openai_models import chat_completion_options, is_reasoning_model


class OpenAIModelConfigTests(unittest.TestCase):
    def test_reasoning_model_uses_reasoning_effort_and_omits_temperature(self):
        options = chat_completion_options(
            model="gpt-5-mini",
            reasoning_effort="high",
            temperature=0.1,
            messages=[{"role": "user", "content": "test"}],
        )

        self.assertEqual(options["model"], "gpt-5-mini")
        self.assertEqual(options["reasoning_effort"], "high")
        self.assertNotIn("temperature", options)
        self.assertTrue(is_reasoning_model(options["model"]))

    def test_non_reasoning_override_keeps_temperature(self):
        options = chat_completion_options(model="gpt-4o-mini", temperature=0.1)

        self.assertEqual(options["model"], "gpt-4o-mini")
        self.assertEqual(options["temperature"], 0.1)
        self.assertNotIn("reasoning_effort", options)
        self.assertFalse(is_reasoning_model(options["model"]))


if __name__ == "__main__":
    unittest.main()
