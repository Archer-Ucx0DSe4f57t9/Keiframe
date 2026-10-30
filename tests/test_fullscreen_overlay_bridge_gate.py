"""Exercise actual bridge method bodies without importing Windows/Qt modules."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


def method(name, namespace):
    path = Path(__file__).resolve().parents[1] / 'src/fullscreen_overlay/bridge.py'
    tree = ast.parse(path.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == 'FullscreenOverlayBridge')
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    module = ast.Module(body=[node], type_ignores=[])
    exec(compile(module, str(path), 'exec'), namespace)
    return namespace[name]


class BridgeGateTests(unittest.TestCase):
    def test_absent_consumer_skips_fullscreen_query_and_render(self):
        fullscreen = Mock(side_effect=AssertionError('must not query windows'))
        callback = method('_publish_if_changed', {'is_sc2_fullscreen': fullscreen})
        bridge = SimpleNamespace(_consume_widget_command=Mock(),
                                 _mailbox=SimpleNamespace(has_consumer=lambda: False))
        callback(bridge)
        fullscreen.assert_not_called()

    def test_active_consumer_without_fullscreen_does_not_render(self):
        fullscreen = Mock(return_value=False)
        callback = method('_publish_if_changed', {'is_sc2_fullscreen': fullscreen})
        bridge = SimpleNamespace(_consume_widget_command=Mock(),
                                 _mailbox=SimpleNamespace(has_consumer=lambda: True))
        callback(bridge)
        fullscreen.assert_called_once()

    def test_command_executes_synchronous_slot(self):
        callback = method('_consume_widget_command', {})
        slot = Mock()
        bridge = SimpleNamespace(owner=SimpleNamespace(process_lock_logic=slot, control_window=object()),
                                 _mailbox=SimpleNamespace(process_commands=lambda f: f()))
        callback(bridge)
        slot.assert_called_once()

    def test_missing_control_window_rejects_command(self):
        callback = method('_consume_widget_command', {})
        slot = Mock()
        bridge = SimpleNamespace(owner=SimpleNamespace(process_lock_logic=slot),
                                 _mailbox=SimpleNamespace(process_commands=lambda f: f()))
        with self.assertRaises(RuntimeError):
            callback(bridge)
        slot.assert_not_called()
