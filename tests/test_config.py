import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def test_control_names_are_unique(self):
        config = json.loads((ROOT / "controls.json").read_text())
        names = [config["output"]["name"]]
        for index in range(config["equalizer"]["max_bands"]):
            names.extend((f"eq.band.{index}.frequency", f"eq.band.{index}.gain", f"eq.band.{index}.q"))
        names.extend((config["tone"]["frequency"]["name"], config["tone"]["amplitude"]["name"]))
        self.assertEqual(len(names), len(set(names)))

    def test_bands_are_in_frequency_order(self):
        config = json.loads((ROOT / "controls.json").read_text())
        frequencies = [band["frequency"] for band in config["bands"]]
        self.assertEqual(frequencies, sorted(frequencies))
        self.assertTrue(all(20 <= frequency <= 20000 for frequency in frequencies))

    def test_default_bands_fit_customization_limits(self):
        config = json.loads((ROOT / "controls.json").read_text())
        limits = config["equalizer"]
        self.assertLessEqual(limits["min_bands"], len(config["bands"]))
        self.assertLessEqual(len(config["bands"]), limits["max_bands"])
        for band in config["bands"]:
            self.assertTrue(limits["gain_min"] <= band["gain"] <= limits["gain_max"])
            self.assertTrue(limits["q_min"] <= band["q"] <= limits["q_max"])

    def test_at_least_40_valid_presets(self):
        config = json.loads((ROOT / "controls.json").read_text())
        data = json.loads((ROOT / "presets.json").read_text())
        self.assertGreaterEqual(len(data["presets"]), 40)
        self.assertEqual(data["frequencies"], sorted(data["frequencies"]))
        names = [preset["name"] for preset in data["presets"]]
        self.assertEqual(len(names), len(set(names)))
        for preset in data["presets"]:
            if "bands" in preset:
                self.assertTrue(config["equalizer"]["min_bands"] <= len(preset["bands"]) <= config["equalizer"]["max_bands"])
                self.assertEqual(
                    [band["frequency"] for band in preset["bands"]],
                    sorted(band["frequency"] for band in preset["bands"]),
                )
                self.assertTrue(all(config["equalizer"]["gain_min"] <= band["gain"] <= config["equalizer"]["gain_max"] for band in preset["bands"]))
                self.assertTrue(all(config["equalizer"]["q_min"] <= band["q"] <= config["equalizer"]["q_max"] for band in preset["bands"]))
            else:
                self.assertEqual(len(preset["gains"]), len(data["frequencies"]))
                self.assertTrue(all(config["equalizer"]["gain_min"] <= gain <= config["equalizer"]["gain_max"] for gain in preset["gains"]))
            if "output_gain" in preset:
                self.assertTrue(config["output"]["min"] <= preset["output_gain"] <= config["output"]["max"])

    def test_generator_creates_runtime_filter_pool(self):
        config = json.loads((ROOT / "controls.json").read_text())
        generated = subprocess.check_output([sys.executable, ROOT / "generate_liquidsoap.py"], text=True)
        self.assertIn('interactive.float("eq.band.count"', generated)
        self.assertIn('interactive.float("eq.band.revision"', generated)
        self.assertEqual(generated.count("radio = filter.iir.eq.peak("), config["equalizer"]["max_bands"])
        self.assertIn('interactive.float("eq.band.0.frequency"', generated)
        self.assertIn(f'interactive.float("eq.band.{config["equalizer"]["max_bands"] - 1}.q"', generated)

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
