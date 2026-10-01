"""Manual Phase D3 runtime-integration test.

Run from the repository root:

    python tests/manual_enemy_composition_runtime_integration.py

The test exercises the production reset slot on ``TimerWindow`` and the
production game-time update adapter with a mock panel detector and OCR
provider.  It does not start Qt, the 6119 scheduler, the screenshot producer,
or any recognizer thread.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import game_state_service, game_time_handler  # noqa: E402
from src.game_readers.enemy_composition_matcher import (  # noqa: E402
    EnemyCompositionMatcher,
)
from src.game_readers.enemy_composition_recognizer import (  # noqa: E402
    EnemyCompositionRecognizer,
    EnemyCompositionState,
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
    def __init__(self) -> None:
        self.calls = 0

    def recognize(self, _image):
        self.calls += 1
        return ["Terran Ground Forces", "Machines of War"]


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
    detector = MockPanelDetector(state.screenshot_lock)
    ocr_provider = MockOCRProvider()
    recognizer = EnemyCompositionRecognizer(
        panel_detector=detector,
        ocr_provider=ocr_provider,
        matcher=EnemyCompositionMatcher(),
        title_crop_extractor=lambda image, _bbox: image.copy(),
    )
    window = SimpleNamespace(
        logger=logger,
        game_state=state,
        enemy_composition_recognizer=recognizer,
        _last_dispatch_game_second=42,
        time_label=SimpleNamespace(setText=lambda _text: None),
    )

    try:
        # Exercise the actual reset_game_info handler used by TimerWindow.
        state.enemy_composition = "Previous composition"
        TimerWindow.handle_progress_update(window, ["reset_game_info"])
        assert recognizer.state == EnemyCompositionState.SEARCHING
        assert state.enemy_composition is None

        state.is_in_game = True
        state.enemy_race = "Terran"
        state.game_time = 30
        frame = np.zeros((120, 160, 3), dtype=np.uint8)

        for timestamp in (1, 2, 3):
            with state.screenshot_lock:
                state.latest_screenshot = frame.copy()
                state.screenshot_timestamp = timestamp
            game_time_handler.update_game_time(window)
            if timestamp < 3:
                assert ocr_provider.calls == 0, ocr_provider.calls
                assert state.enemy_composition is None

        assert detector.calls == 3, detector.calls
        assert ocr_provider.calls == 3, ocr_provider.calls
        assert recognizer.state == EnemyCompositionState.CONFIRMED
        assert state.enemy_composition == "Machines of War"

        print("reset_game_info: PASS")
        print("panel frames: 3")
        print(f"mock OCR calls: {ocr_provider.calls}")
        print(f"enemy_composition: {state.enemy_composition}")
        print("PHASE_D3_RUNTIME_INTEGRATION = PASS")
        return 0
    finally:
        state.enemy_race = saved_state["enemy_race"]
        state.active_mutators = saved_state["active_mutators"]
        state.enemy_composition = saved_state["enemy_composition"]
        state.game_time = saved_state["game_time"]
        state.is_in_game = saved_state["is_in_game"]
        state.latest_screenshot = saved_state["latest_screenshot"]
        state.screenshot_timestamp = saved_state["screenshot_timestamp"]


if __name__ == "__main__":
    raise SystemExit(main())
