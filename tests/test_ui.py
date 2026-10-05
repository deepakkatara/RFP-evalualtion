import unittest
from streamlit.testing.v1 import AppTest


class UiTests(unittest.TestCase):
    def test_app_starts_without_exception(self):
        app = AppTest.from_file("streamlit_app.py")
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Configuration & Evaluation Metrics" in item.value for item in app.subheader))
        self.assertTrue(any("Upload at least two proposal PDFs" in item.value for item in app.info))


if __name__ == "__main__":
    unittest.main()
