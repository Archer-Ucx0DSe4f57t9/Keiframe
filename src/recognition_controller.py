"""Recognition pipeline assembly and result coordination for ``TimerWindow``."""

from src import game_state_service
from src.game_readers.enemy_composition_matcher import EnemyCompositionMatcher
from src.game_readers.enemy_composition_panel_detector import (
    detect_enemy_composition_panel,
)
from src.game_readers.enemy_composition_recognizer import EnemyCompositionRecognizer
from src.game_readers.enemy_composition_scheduler import EnemyCompositionScheduler
from src.game_readers.ppocr_opencv_provider import OpenCVDNNPPOCRv5Provider
from src.map_handlers import map_loader


def create_production_enemy_composition_ocr_provider(logger):
    """Initialize the optional OpenCV DNN PP-OCRv5 backend once.

    Enemy Composition is optional at runtime: a missing dependency, model,
    dictionary, or failed OpenCV initialization must not prevent the rest of
    KeiFrame from starting. The caller keeps the returned instance for the
    lifetime of ``TimerWindow``; game resets only reset recognizer state.
    """

    try:
        provider = OpenCVDNNPPOCRv5Provider()
    except Exception as exc:  # Optional OCR must not break the main window.
        reason = str(exc) or type(exc).__name__
        logger.warning(
            "Enemy Composition OCR addon unavailable: %s",
            reason,
        )
        return None

    logger.info("Enemy Composition OpenCV PP-OCRv5 backend initialized")
    return provider


class RecognitionController:
    """Assemble recognizers and coordinate confirmed recognition results."""

    def __init__(
        self,
        window,
        game_state=game_state_service.state,
        map_loader_module=map_loader,
    ):
        self.window = window
        self.game_state = game_state
        self.map_loader = map_loader_module

    def initialize_enemy_composition_recognition(self):
        """Assemble the optional production Enemy Composition pipeline once."""

        window = self.window
        window.enemy_composition_matcher = EnemyCompositionMatcher()
        window.enemy_composition_panel_detector = detect_enemy_composition_panel
        window.enemy_composition_ocr_provider = (
            create_production_enemy_composition_ocr_provider(window.logger)
        )
        window.enemy_composition_recognizer = None
        window.enemy_composition_scheduler = None

        if window.enemy_composition_ocr_provider is None:
            # Explicitly detach any previous scheduler if this method is ever
            # reused by a caller; no frame should reach a disabled pipeline.
            window.mutator_and_enemy_race_recognizer.set_enemy_composition_scheduler(
                None
            )
            window.logger.info("Enemy composition recognition disabled")
            return

        window.enemy_composition_recognizer = EnemyCompositionRecognizer(
            panel_detector=window.enemy_composition_panel_detector,
            ocr_provider=window.enemy_composition_ocr_provider,
            matcher=window.enemy_composition_matcher,
        )
        confirmation_signal = getattr(
            window,
            "enemy_composition_confirmed_signal",
            None,
        )
        confirmation_callback = getattr(confirmation_signal, "emit", None)
        window.enemy_composition_scheduler = EnemyCompositionScheduler(
            recognizer=window.enemy_composition_recognizer,
            game_state=window.game_state,
            logger=window.logger,
            confirmation_callback=confirmation_callback,
        )
        window.mutator_and_enemy_race_recognizer.set_enemy_composition_scheduler(
            window.enemy_composition_scheduler
        )
        window.logger.info("Enemy composition recognizer initialized")

    def handle_enemy_composition_confirmed(self, canonical_composition):
        """Render a worker confirmation after filtering stale results."""

        window = self.window
        if getattr(window, "_safe_exiting", False):
            return
        if not canonical_composition:
            return

        # The scheduler publishes GlobalState before emitting the signal. A
        # reset can be queued concurrently; checking the published fact here
        # prevents a stale queued confirmation from showing in the next game.
        if (
            getattr(window.game_state, "enemy_composition", None)
            != canonical_composition
        ):
            window.logger.debug(
                "Ignoring stale Enemy Composition confirmation: %s",
                canonical_composition,
            )
            return

        notifier = getattr(window, "enemy_composition_notifier", None)
        if notifier is not None:
            notifier.show(canonical_composition)

    def handle_mutator_and_enemy_race_recognition_update(self, results):
        """Coordinate race and mutator recognition with map/button state."""

        window = self.window
        race = results.get("race")
        mutators = results.get("mutators")

        if race:
            window.logger.info(f"UI接收到确认种族: {race}")
            self.game_state.enemy_race = race

            current_map = window.combo_box.currentText()
            if current_map:
                self.map_loader.handle_map_selection(window, current_map)
            # 如果种族更新，强制同步突变因子按钮状态
            if (
                hasattr(window, "mutator_manager")
                and window.mutator_manager
                and self.game_state.active_mutators is not None
            ):
                window.logger.info(
                    f"种族已更新{race}，强制重新同步突变因子变式。"
                )
                window.mutator_manager.sync_mutator_toggles(
                    self.game_state.active_mutators
                )

        if mutators is not None:
            # None means recognition is incomplete; an empty list is a
            # completed recognition and must still clear/sync the buttons.
            window.logger.info(f"UI接收到确认突变因子: {mutators}")
            self.game_state.active_mutators = mutators
            if hasattr(window, "mutator_manager") and window.mutator_manager:
                window.mutator_manager.sync_mutator_toggles(mutators)


__all__ = [
    "RecognitionController",
    "create_production_enemy_composition_ocr_provider",
]
