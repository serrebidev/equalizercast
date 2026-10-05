import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


SPEC = importlib.util.spec_from_file_location("equalizercast_app", Path(__file__).resolve().parents[1] / "app.py")
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


class ToneTimerTests(unittest.TestCase):
    def setUp(self):
        self.timer_patch = patch.object(app.threading, "Timer")
        self.timer = self.timer_patch.start()
        self.timer.side_effect = lambda *args, **kwargs: Mock()
        self.addCleanup(self.timer_patch.stop)
        self.runtime_patch = patch.object(app, "runtime_set")
        self.runtime_patch.start()
        self.addCleanup(self.runtime_patch.stop)
        self.addCleanup(app.STATE.__setitem__, "eq.tone.enabled", app.STATE["eq.tone.enabled"])
        app.TONE_TIMER = None
        self.addCleanup(setattr, app, "TONE_TIMER", None)

    def test_stopping_tone_cancels_pending_timeout(self):
        app.start_tone_timer()
        pending = app.TONE_TIMER
        app.stop_tone()
        pending.cancel.assert_called_once()
        self.assertIsNone(app.TONE_TIMER)

    def test_old_timeout_cannot_stop_restarted_tone(self):
        app.start_tone_timer()
        old_callback = self.timer.call_args.args[1]
        app.stop_tone()
        app.start_tone_timer()
        current = app.TONE_TIMER
        app.STATE["eq.tone.enabled"] = True
        old_callback()
        self.assertTrue(app.STATE["eq.tone.enabled"])
        self.assertIs(app.TONE_TIMER, current)


if __name__ == "__main__":
    unittest.main()
