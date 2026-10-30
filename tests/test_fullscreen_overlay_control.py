import json
import tempfile
import unittest
from pathlib import Path
from src.fullscreen_overlay.control import atomic_json, live_session, process_commands

SESSION = 'a' * 32
COMMAND = 'b' * 32


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.calls = []

    def heartbeat(self, timestamp=100):
        atomic_json(self.folder / 'overlay.heartbeat',
                    dict(version=1, session=SESSION, updated_at=timestamp))

    def command(self, **overrides):
        data = dict(version=1, id=COMMAND, session=SESSION,
                    action='toggle_lock', created_at=100)
        data.update(overrides)
        atomic_json(self.folder / f'overlay.command.{COMMAND}.json', data)

    def execute(self):
        self.calls.append('toggle')

    def ack(self):
        return json.loads((self.folder / f'overlay.ack.{COMMAND}.json').read_text())

    def test_absent_expired_malformed_and_future_lease_are_inactive(self):
        self.assertIsNone(live_session(self.folder, 100))
        self.heartbeat()
        self.assertEqual(live_session(self.folder, 102), SESSION)
        self.assertIsNone(live_session(self.folder, 104))
        self.assertIsNone(live_session(self.folder, 99))
        (self.folder / 'overlay.heartbeat').write_text('{}')
        self.assertIsNone(live_session(self.folder, 100))

    def test_partial_publication_is_not_consumed(self):
        self.heartbeat()
        pending = self.folder / f'overlay.command.{COMMAND}.json.tmp'
        pending.write_text('')
        process_commands(self.folder, self.execute, 100)
        self.assertTrue(pending.exists())
        self.assertEqual(self.calls, [])
        self.command()
        process_commands(self.folder, self.execute, 100)
        self.assertEqual(self.calls, ['toggle'])
        self.assertTrue(self.ack()['ok'])

    def test_duplicate_publication_with_ack_does_not_toggle_twice(self):
        self.heartbeat()
        for _ in range(2):
            self.command()
            process_commands(self.folder, self.execute, 100)
        self.assertEqual(self.calls, ['toggle'])

    def test_invalid_session_and_expired_commands_are_rejected(self):
        self.heartbeat()
        self.command(session='c' * 32)
        process_commands(self.folder, self.execute, 100)
        self.assertFalse(self.ack()['ok'])
        self.assertEqual(self.calls, [])

    def test_stale_command_is_rejected_even_with_fresh_heartbeat(self):
        self.heartbeat()
        self.command(created_at=90)
        process_commands(self.folder, self.execute, 100)
        self.assertFalse(self.ack()['ok'])
        self.assertEqual(self.calls, [])

    def test_execution_failure_is_not_acknowledged_as_success(self):
        self.heartbeat()
        self.command()
        def fail():
            raise RuntimeError('failed')
        process_commands(self.folder, fail, 100)
        self.assertFalse(self.ack()['ok'])
        self.assertEqual(self.ack()['error'], 'failed')

    def test_claimed_command_is_not_replayed(self):
        self.heartbeat()
        self.command()
        path = self.folder / f'overlay.command.{COMMAND}.json'
        path.rename(path.with_suffix('.processing'))
        process_commands(self.folder, self.execute, 100)
        self.assertEqual(self.calls, [])

    def test_missing_folder_not_created(self):
        missing = self.folder / 'absent'
        process_commands(missing, self.execute, 100)
        self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
