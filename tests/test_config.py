import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_control_names_are_unique(self):
        config = json.loads((ROOT / "controls.json").read_text())
        names = [config["output"]["name"]]
        names.extend(f"eq.gain.{band['frequency']}" for band in config["bands"])
        names.extend((config["tone"]["frequency"]["name"], config["tone"]["amplitude"]["name"]))
        self.assertEqual(len(names), len(set(names)))

    def test_bands_are_in_frequency_order(self):
        config = json.loads((ROOT / "controls.json").read_text())
        frequencies = [band["frequency"] for band in config["bands"]]
        self.assertEqual(frequencies, sorted(frequencies))
        self.assertTrue(all(20 <= frequency <= 20000 for frequency in frequencies))

    def test_no_runtime_secrets_are_tracked(self):
        forbidden = (
            "LIQUIDSOAP_API_KEY" + "=",
            "x-liquidsoap-api-key" + ": ",
            "MYSQL" + "_PASSWORD",
        )
        for path in ROOT.rglob("*"):
            if path.is_file() and ".git" not in path.parts and "__pycache__" not in path.parts:
                text = path.read_text(errors="ignore")
                for marker in forbidden:
                    self.assertNotIn(marker, text, f"{marker!r} found in {path}")


if __name__ == "__main__":
    unittest.main()
