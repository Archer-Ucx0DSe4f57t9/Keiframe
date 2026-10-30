"""Dependency-free lifecycle regressions for the real AppRuntime methods.

Compile the class AST without its Windows/Qt imports; collaborators are fakes.
This validates lifecycle behavior, not a real Qt or Windows startup.
"""
import ast
from pathlib import Path
import sys
import traceback
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def load_runtime():
    path = ROOT / "src/app_runtime.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                and node.name == "AppRuntime")
    namespace = {
        "config": SimpleNamespace(ENABLE_GAMEBAR_OVERLAY=True),
        "traceback": traceback,
        "sys": SimpleNamespace(platform="test"),
        "game_state_service": SimpleNamespace(state=SimpleNamespace(app_closing=False)),
        "config_hotkeys": SimpleNamespace(unhook_global_hotkeys=Mock()),
        "QApplication": SimpleNamespace(instance=lambda: None),
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["AppRuntime"], namespace


class OverlayRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.runtime_class, self.env = load_runtime()
        self.window = SimpleNamespace(logger=Mock(), malwarfare_handler=None)
        self.runtime = self.runtime_class(self.window)
        self.bridge = Mock()
        self.factory = Mock(return_value=self.bridge)
        self.module = ModuleType("src.fullscreen_overlay.bridge")
        self.module.FullscreenOverlayBridge = self.factory

    def initialize(self):
        with patch.dict(sys.modules, {"src.fullscreen_overlay.bridge": self.module}):
            self.runtime._initialize_fullscreen_overlay()

    def test_enabled_bridge_is_owned_by_window_and_started(self):
        self.initialize()
        self.factory.assert_called_once_with(self.window)
        self.bridge.start.assert_called_once_with()
        self.assertIs(self.window.fullscreen_overlay_bridge, self.bridge)

    def test_disabled_bridge_is_not_created(self):
        self.env["config"].ENABLE_GAMEBAR_OVERLAY = False
        self.initialize()
        self.factory.assert_not_called()
        self.assertIsNone(self.window.fullscreen_overlay_bridge)

    def test_old_configuration_defaults_to_enabled(self):
        del self.env["config"].ENABLE_GAMEBAR_OVERLAY
        self.initialize()
        self.bridge.start.assert_called_once_with()

    def test_failed_start_stops_partial_bridge_without_raising(self):
        self.bridge.start.side_effect = RuntimeError("start failed")
        self.initialize()
        self.bridge.stop.assert_called_once_with()
        self.assertIsNone(self.window.fullscreen_overlay_bridge)
        self.window.logger.error.assert_called()

    def test_stop_is_idempotent(self):
        self.window.fullscreen_overlay_bridge = self.bridge
        self.runtime._stop_fullscreen_overlay()
        self.runtime._stop_fullscreen_overlay()
        self.bridge.stop.assert_called_once_with()

    def test_both_exit_paths_stop_bridge_before_other_components(self):
        for method in ("safe_exit", "cleanup_on_close"):
            with self.subTest(method=method):
                events = []
                self.window._safe_exiting = False
                self.window.fullscreen_overlay_bridge = SimpleNamespace(
                    stop=lambda: events.append("overlay"))
                self.window.toast_manager = SimpleNamespace(
                    shutdown=lambda: events.append("toast"))
                getattr(self.runtime, method)()
                self.assertEqual(events[:2], ["overlay", "toast"])
                self.assertIsNone(self.window.fullscreen_overlay_bridge)

    def test_bridge_stop_failure_does_not_skip_remaining_cleanup(self):
        for method in ("safe_exit", "cleanup_on_close"):
            with self.subTest(method=method):
                self.window._safe_exiting = False
                self.window.fullscreen_overlay_bridge = self.bridge
                self.bridge.stop.side_effect = RuntimeError("stop failed")
                self.window.toast_manager = Mock()
                getattr(self.runtime, method)()
                self.window.toast_manager.shutdown.assert_called_once_with()

    def test_bridge_starts_after_show_before_delayed_lock(self):
        events = []
        self.window.show = lambda: events.append("show")
        self.runtime._initialize_fullscreen_overlay = lambda: events.append("overlay")
        self.env["QTimer"] = SimpleNamespace(
            singleShot=lambda interval, callback: events.append(("delay", interval)))
        self.runtime._show_initial_window_state()
        self.assertEqual(events, ["show", "overlay", ("delay", 100)])


class BuildEntryContractTests(unittest.TestCase):
    def test_ps1_delegates_to_canonical_batch_without_resource_copy(self):
        script = (ROOT / "build-keiframe.ps1").read_text(encoding="utf-8")
        self.assertIn('"build-keiframe.bat"', script)
        self.assertIn("& $scriptPath", script)
        self.assertNotIn("Copy-Item", script)
        batch = (ROOT / "build-keiframe.bat").read_text(encoding="utf-8")
        self.assertNotIn("build-keiframe.ps1", batch)
        self.assertIn('/XD "%OCR_SOURCE_DIR%"', batch)
        self.assertIn("KeiFrame_PP-OCRv5_Addon", batch)

    def test_tests_are_not_ignored(self):
        lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertNotIn("/tests", lines)
        self.assertIn("gamebar/**/obj/", lines)


if __name__ == "__main__":
    unittest.main()
