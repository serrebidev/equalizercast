import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


SPEC = importlib.util.spec_from_file_location("equalizercast_app_reset", Path(__file__).resolve().parents[1] / "app.py")
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


class ResetTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, app, "BANDS", app.BANDS)
        saved_state = app.STATE.copy()
        self.addCleanup(lambda: (app.STATE.clear(), app.STATE.update(saved_state)))

    def test_refused_reset_keeps_the_current_settings(self):
        output = app.CONTROLS["output"]["name"]
        app.STATE[output] = app.DEFAULTS[output] + 1.0
        app.BANDS = [{**band, "gain": 3.0} for band in app.DEFAULT_BANDS]
        before_state, before_bands = app.STATE.copy(), [band.copy() for band in app.BANDS]
        handler = Mock()

        with patch.object(app, "runtime_set", side_effect=RuntimeError("Liquidsoap is down")), \
                patch.object(app, "save_state") as save_state:
            with self.assertRaises(RuntimeError):
                app.Handler.handle_reset(handler)

        self.assertEqual(app.STATE, before_state)
        self.assertEqual(app.BANDS, before_bands)
        save_state.assert_not_called()


if __name__ == "__main__":
    unittest.main()
