import builtins
import io
import logging
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from src.utils import fileutil, logging_util


class LoggingPathTests(unittest.TestCase):
    def test_source_and_frozen_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / 'project'
            source_file = project_root / 'src' / 'utils' / 'fileutil.py'
            executable = Path(temp_dir) / 'dist' / 'KeiFrame.exe'

            with mock.patch.object(fileutil, '__file__', str(source_file)), mock.patch.object(
                sys, 'frozen', False, create=True
            ):
                self.assertEqual(fileutil.get_project_root(), str(project_root))
                self.assertEqual(
                    fileutil.get_log_file_path(),
                    str(project_root / 'Keiframe.log'),
                )

            with mock.patch.object(sys, 'frozen', True, create=True), mock.patch.object(
                sys, 'executable', str(executable)
            ):
                self.assertEqual(fileutil.get_project_root(), str(executable.parent))
                self.assertEqual(
                    fileutil.get_log_file_path(),
                    str(executable.parent / 'Keiframe.log'),
                )

    def test_log_path_does_not_depend_on_current_working_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / 'project'
            source_file = project_root / 'src' / 'utils' / 'fileutil.py'
            other_directory = Path(temp_dir) / 'other'
            other_directory.mkdir()
            original_cwd = os.getcwd()
            try:
                os.chdir(other_directory)
                with mock.patch.object(fileutil, '__file__', str(source_file)), mock.patch.object(
                    sys, 'frozen', False, create=True
                ):
                    self.assertEqual(
                        fileutil.get_log_file_path(),
                        str(project_root / 'Keiframe.log'),
                    )
            finally:
                os.chdir(original_cwd)


class LoggingInitializationTests(unittest.TestCase):
    def setUp(self):
        self.original_handlers = logging.root.handlers[:]
        self.original_level = logging.root.level
        logging.root.handlers = []

    def tearDown(self):
        self._close_current_handlers()
        logging.root.handlers = self.original_handlers
        logging.root.setLevel(self.original_level)

    def _close_current_handlers(self):
        for handler in logging.root.handlers:
            handler.close()
        logging.root.handlers = []

    def test_default_writable_path_is_used(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            default_log = Path(temp_dir) / 'program' / 'Keiframe.log'
            fallback_log = Path(temp_dir) / 'local' / 'Keiframe.log'

            selected = logging_util.resolve_log_file_path(
                str(default_log), str(fallback_log)
            )
            configured = logging_util.setup_logger(log_file_path=selected)
            logging.getLogger('logging-startup-test').warning('default path message')
            for handler in logging.root.handlers:
                handler.flush()

            self.assertEqual(configured, str(default_log))
            self.assertIn('default path message', default_log.read_text(encoding='utf-8'))
            self.assertFalse(fallback_log.exists())
            self._close_current_handlers()

    def test_handlers_include_logger_name_and_preserve_level_filtering(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / 'Keiframe.log'
            stream = io.StringIO()

            with mock.patch.object(logging_util.config, 'LOG_LEVEL', 'WARNING'):
                logging_util.setup_logger(log_file_path=str(log_file))
            try:
                stream_handler = next(
                    handler
                    for handler in logging.root.handlers
                    if type(handler) is logging.StreamHandler
                )
                stream_handler.setStream(stream)
                module_logger = logging_util.get_logger(__name__)
                explicit_logger = logging_util.get_logger('setting window')
                module_logger.debug('filtered debug message')
                module_logger.warning('module logger message')
                explicit_logger.error('explicit logger message')
                for handler in logging.root.handlers:
                    handler.flush()

                expected_format = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
                self.assertTrue(logging.root.handlers)
                self.assertTrue(
                    all(
                        handler.formatter._fmt == expected_format
                        for handler in logging.root.handlers
                    )
                )

                file_output = log_file.read_text(encoding='utf-8')
                stream_output = stream.getvalue()
                for output in (file_output, stream_output):
                    self.assertIn(
                        f' - WARNING - {__name__} - module logger message', output
                    )
                    self.assertIn(
                        ' - ERROR - setting window - explicit logger message', output
                    )
                    self.assertNotIn('filtered debug message', output)
            finally:
                self._close_current_handlers()

    def test_permission_error_falls_back_to_local_appdata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            default_log = Path(temp_dir) / 'program' / 'Keiframe.log'
            local_appdata = Path(temp_dir) / 'local-app-data'
            fallback_log = local_appdata / 'Keiframe' / 'logs' / 'Keiframe.log'
            real_open = builtins.open

            def permission_guard(path, *args, **kwargs):
                if os.path.abspath(os.fspath(path)) == os.path.abspath(default_log):
                    raise PermissionError('simulated default log permission error')
                return real_open(path, *args, **kwargs)

            with mock.patch.dict(os.environ, {'LOCALAPPDATA': str(local_appdata)}), mock.patch(
                'builtins.open', side_effect=permission_guard
            ):
                selected = logging_util.resolve_log_file_path(str(default_log))

            configured = logging_util.setup_logger(log_file_path=selected)
            logging.getLogger('logging-startup-test').warning('fallback path message')
            for handler in logging.root.handlers:
                handler.flush()

            self.assertEqual(selected, str(fallback_log))
            self.assertEqual(configured, str(fallback_log))
            self.assertTrue(fallback_log.parent.is_dir())
            self.assertIn('fallback path message', fallback_log.read_text(encoding='utf-8'))
            self._close_current_handlers()

    def test_two_unwritable_paths_degrade_to_stream_logging(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            default_log = Path(temp_dir) / 'program' / 'Keiframe.log'
            fallback_log = Path(temp_dir) / 'local' / 'Keiframe.log'

            with mock.patch('builtins.open', side_effect=PermissionError('simulated')):
                selected = logging_util.resolve_log_file_path(
                    str(default_log), str(fallback_log)
                )

            configured = logging_util.setup_logger(log_file_path=selected)
            logging.getLogger('logging-startup-test').warning('stream-only message')

            self.assertIsNone(selected)
            self.assertIsNone(configured)
            self.assertFalse(
                any(isinstance(handler, logging.FileHandler) for handler in logging.root.handlers)
            )
            self.assertTrue(
                any(type(handler) is logging.StreamHandler for handler in logging.root.handlers)
            )

    def test_file_handler_permission_error_is_safe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = str(Path(temp_dir) / 'Keiframe.log')
            with mock.patch.object(
                logging, 'FileHandler', side_effect=PermissionError('simulated')
            ):
                configured = logging_util.setup_logger(log_file_path=log_file)

            self.assertIsNone(configured)
            self.assertTrue(
                any(type(handler) is logging.StreamHandler for handler in logging.root.handlers)
            )

    def test_large_log_rotation_keeps_recent_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / 'Keiframe.log'
            old_date = (datetime.now() - timedelta(days=8)).strftime('%Y-%m-%d')
            recent_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            old_line = f'{old_date} old entry ' + ('x' * (1024 * 1024)) + '\n'
            recent_line = f'{recent_date} recent entry\n'
            log_file.write_text(old_line + recent_line, encoding='utf-8')

            self.assertTrue(logging_util.rotate_log_file(str(log_file)))
            rotated = log_file.read_text(encoding='utf-8')

            self.assertNotIn('old entry', rotated)
            self.assertIn('recent entry', rotated)

    def test_rotation_permission_error_is_safe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / 'Keiframe.log'
            log_file.write_text('x' * (1024 * 1024 + 1), encoding='utf-8')

            with mock.patch('builtins.open', side_effect=PermissionError('simulated')):
                self.assertFalse(logging_util.rotate_log_file(str(log_file)))

    def test_custom_base_dir_keeps_legacy_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            configured = logging_util.setup_logger(base_dir=temp_dir)
            expected_log = Path(temp_dir) / 'log' / 'sc2_Keiframe.log'
            logging.getLogger('logging-startup-test').warning('legacy path message')
            for handler in logging.root.handlers:
                handler.flush()

            self.assertEqual(configured, str(expected_log))
            self.assertIn('legacy path message', expected_log.read_text(encoding='utf-8'))
            self._close_current_handlers()

    def test_startup_rotation_and_setup_share_selected_path(self):
        selected = os.path.join('selected', 'Keiframe.log')
        with mock.patch.object(
            logging_util, 'resolve_log_file_path', return_value=selected
        ), mock.patch.object(logging_util, 'rotate_log_file') as rotate, mock.patch.object(
            logging_util, 'setup_logger', return_value=selected
        ) as setup:
            self.assertEqual(logging_util.initialize_logging(), selected)

        rotate.assert_called_once_with(selected)
        setup.assert_called_once_with(log_file_path=selected)


if __name__ == '__main__':
    unittest.main()
