"""Manual Phase D4.1 runtime-integration test.

Run from the repository root:

    python tests/manual_enemy_composition_runtime_integration.py

The test exercises the production reset slot on ``TimerWindow`` and the
perception-loop scheduler with a mock panel detector and OCR provider.  It
does not start Qt, the 6119 scheduler, the screenshot producer, or any
recognizer thread.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import game_state_service  # noqa: E402
from src.game_readers.enemy_composition_matcher import (  # noqa: E402
    EnemyCompositionMatcher,
)
from src.game_readers.enemy_composition_recognizer import (  # noqa: E402
    EnemyCompositionRecognizer,
    EnemyCompositionState,
)
from src.game_readers.enemy_composition_scheduler import (  # noqa: E402
    EnemyCompositionScheduler,
)
from src.qt_gui import TimerWindow  # noqa: E402


class MockPanelDetector:
    def __init__(self, screenshot_lock) -> None:
        self.calls = 0
        self.screenshot_lock = screenshot_lock

    def detect(self, image):
        self.calls += 1
        lock_available = self.screenshot_lock.acquire(blocking=False)
        assert lock_available, "screenshot_lock was held during panel detection"
        self.screenshot_lock.release()
        height, width = image.shape[:2]
        return SimpleNamespace(found=True, bbox=(0, 0, width, height))


class MockOCRProvider:
    def __init__(self, outputs) -> None:
        self._outputs = iter(outputs)
        self.calls = 0

    def recognize(self, _image):
        self.calls += 1
        return next(self._outputs)


class DiagnosticLogHandler(logging.Handler):
    """Capture the recognizer's timing chain without changing production code."""

    def __init__(self) -> None:
        super().__init__()
        self.events = []

    def emit(self, record) -> None:
        message = record.getMessage()
        if message.startswith("[EnemyComposition]") or "Enemy composition confirmed:" in message:
            self.events.append((time.perf_counter(), message))


def make_pipeline(state, ocr_outputs):
    detector = MockPanelDetector(state.screenshot_lock)
    ocr_provider = MockOCRProvider(ocr_outputs)
    recognizer = EnemyCompositionRecognizer(
        panel_detector=detector,
        ocr_provider=ocr_provider,
        matcher=EnemyCompositionMatcher(),
        title_crop_extractor=lambda image, _bbox: image.copy(),
    )
    scheduler = EnemyCompositionScheduler(
        recognizer=recognizer,
        game_state=state,
        logger=logging.getLogger("manual_enemy_composition_runtime_integration"),
    )
    return detector, ocr_provider, recognizer, scheduler


def report_timing(case_name, case_start, events) -> None:
    panel_found_at = next(
        (event_time for event_time, message in events if "PANEL_FOUND" in message),
        None,
    )
    ocr_start_at = next(
        (event_time for event_time, message in events if "OCR_START" in message),
        None,
    )
    confirmed_at = next(
        (
            event_time
            for event_time, message in events
            if "Enemy composition confirmed:" in message
        ),
        None,
    )

    if panel_found_at is None:
        raise AssertionError(f"{case_name}: PANEL_FOUND log missing")
    if ocr_start_at is None:
        raise AssertionError(f"{case_name}: OCR_START log missing")

    print(f"{case_name} diagnostic logs:")
    for _event_time, message in events:
        print(message)

    panel_to_ocr_ms = (ocr_start_at - panel_found_at) * 1000
    print(f"{case_name} PANEL_FOUND -> OCR_START: {panel_to_ocr_ms:.2f} ms")
    if confirmed_at is None:
        print(f"{case_name} PANEL_FOUND -> CONFIRMED: not reached")
    else:
        panel_to_confirmed_ms = (confirmed_at - panel_found_at) * 1000
        print(
            f"{case_name} PANEL_FOUND -> CONFIRMED: "
            f"{panel_to_confirmed_ms:.2f} ms"
        )
    print(
        f"{case_name} elapsed from case start: "
        f"{(time.perf_counter() - case_start) * 1000:.2f} ms"
    )


def run_case(state, case_name, ocr_outputs, log_handler, pipeline=None):
    if pipeline is None:
        pipeline = make_pipeline(state, ocr_outputs)
    detector, ocr_provider, recognizer, scheduler = pipeline

    state.enemy_composition = None
    state.is_in_game = True
    state.enemy_race = "Terran"
    state.game_time = 30
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    log_handler.events.clear()
    case_start = time.perf_counter()

    for timestamp in (1, 2, 3):
        with state.screenshot_lock:
            state.latest_screenshot = frame.copy()
            state.screenshot_timestamp = timestamp
        scheduler.update()
        if timestamp < 3:
            assert ocr_provider.calls == 0, ocr_provider.calls
            assert state.enemy_composition is None

    assert detector.calls == 3, detector.calls
    assert len(recognizer.collected_crops) == 3
    assert recognizer.config.max_crops == 3
    assert recognizer.config.minimum_valid_results == 2
    assert recognizer.config.minimum_votes == 2
    report_timing(case_name, case_start, log_handler.events)
    return detector, ocr_provider, recognizer, scheduler


def main() -> int:
    state = game_state_service.state
    saved_state = {
        "enemy_race": state.enemy_race,
        "active_mutators": state.active_mutators,
        "enemy_composition": state.enemy_composition,
        "game_time": state.game_time,
        "is_in_game": state.is_in_game,
        "latest_screenshot": state.latest_screenshot,
        "screenshot_timestamp": state.screenshot_timestamp,
    }

    logger = logging.getLogger("manual_enemy_composition_runtime_integration")
    logger.addHandler(logging.NullHandler())
    recognizer_logger = logging.getLogger(
        "src.game_readers.enemy_composition_recognizer"
    )
    diagnostic_handler = DiagnosticLogHandler()
    previous_level = recognizer_logger.level
    recognizer_logger.setLevel(logging.DEBUG)
    recognizer_logger.addHandler(diagnostic_handler)

    try:
        first_pipeline = make_pipeline(
            state,
            ["Machines of War", "Machines of War"],
        )
        _detector, _ocr_provider, first_recognizer, first_scheduler = first_pipeline

        # Exercise the actual reset_game_info handler used by TimerWindow.
        state.enemy_composition = "Previous composition"
        window = SimpleNamespace(
            logger=logger,
            game_state=state,
            enemy_composition_recognizer=first_recognizer,
            enemy_composition_scheduler=first_scheduler,
            _last_dispatch_game_second=42,
            time_label=SimpleNamespace(setText=lambda _text: None),
        )
        TimerWindow.handle_progress_update(window, ["reset_game_info"])
        assert first_recognizer.state == EnemyCompositionState.SEARCHING
        assert state.enemy_composition is None
        print("reset_game_info: PASS")

        _detector, ocr_provider, recognizer, _scheduler = run_case(
            state,
            "two consistent OCR results",
            ["Machines of War", "Machines of War"],
            diagnostic_handler,
            pipeline=first_pipeline,
        )
        assert ocr_provider.calls == 2, ocr_provider.calls
        assert recognizer.state == EnemyCompositionState.CONFIRMED
        assert state.enemy_composition == "Machines of War"
        print("two consistent OCR results: PASS")

        _detector, ocr_provider, recognizer, _scheduler = run_case(
            state,
            "UNKNOWN plus two consistent OCR results",
            ["UNKNOWN", "Machines of War", "Machines of War"],
            diagnostic_handler,
        )
        assert ocr_provider.calls == 3, ocr_provider.calls
        assert recognizer.state == EnemyCompositionState.CONFIRMED
        assert state.enemy_composition == "Machines of War"
        print("UNKNOWN plus two consistent OCR results: PASS")

        _detector, ocr_provider, recognizer, _scheduler = run_case(
            state,
            "two different OCR results",
            ["Machines of War", "Shadow Tech", "UNKNOWN"],
            diagnostic_handler,
        )
        assert ocr_provider.calls == 3, ocr_provider.calls
        assert recognizer.state == EnemyCompositionState.CONFIRMING
        assert state.enemy_composition is None
        print("two different OCR results: PASS")

        print("default max_crops=3: PASS")
        print("PHASE_D4.1_EARLY_CONFIRM = PASS")
        return 0
    finally:
        recognizer_logger.removeHandler(diagnostic_handler)
        recognizer_logger.setLevel(previous_level)
        state.enemy_race = saved_state["enemy_race"]
        state.active_mutators = saved_state["active_mutators"]
        state.enemy_composition = saved_state["enemy_composition"]
        state.game_time = saved_state["game_time"]
        state.is_in_game = saved_state["is_in_game"]
        state.latest_screenshot = saved_state["latest_screenshot"]
        state.screenshot_timestamp = saved_state["screenshot_timestamp"]


if __name__ == "__main__":
    raise SystemExit(main())
