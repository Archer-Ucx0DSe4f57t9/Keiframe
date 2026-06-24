from dataclasses import asdict, dataclass


@dataclass
class CradleOfDeathWaveState:
    phase: int
    wave_index: int
    phase_start_game_second: int
    target_game_second: int
    army_strength: str
    alert_id: str
    status: str


class CradleOfDeathWaveManager:
    ALERT_LEAD_SECONDS = 30
    EVENT_NAME = "偷车波次"

    STATUS_PENDING = "pending"
    STATUS_ALERTING = "alerting"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED_BY_NEXT_PHASE = "cancelled_by_next_phase"

    PHASE_WAVES = {
        1: ((180, "t1s1"), (300, "t1s1")),
        2: ((105, "t1s2"), (165, "t2s2"), (280, "t2s2")),
        3: ((135, "t3s2"), (195, "t3s2"), (250, "t3s3")),
    }

    def __init__(self, toast_manager, logger=None):
        self.toast_manager = toast_manager
        self.logger = logger
        self._wave_states = []
        self._current_phase = None
        self._last_processed_game_second = None

    def on_phase_started(self, phase, phase_start_game_second):
        phase = int(phase)
        phase_start_game_second = int(phase_start_game_second)

        if self._current_phase == phase:
            return

        self._cancel_unfinished_previous_phase_waves(phase)
        self._current_phase = phase
        self._last_processed_game_second = None

        if phase not in self.PHASE_WAVES:
            self._log_debug(f"未知的死亡摇篮偷车阶段: {phase}")
            return

        existing_alert_ids = {wave.alert_id for wave in self._wave_states}
        for wave_index, (offset_seconds, army_strength) in enumerate(self.PHASE_WAVES[phase], start=1):
            alert_id = self._build_alert_id(phase, wave_index)
            if alert_id in existing_alert_ids:
                continue

            self._wave_states.append(
                CradleOfDeathWaveState(
                    phase=phase,
                    wave_index=wave_index,
                    phase_start_game_second=phase_start_game_second,
                    target_game_second=phase_start_game_second + offset_seconds,
                    army_strength=army_strength,
                    alert_id=alert_id,
                    status=self.STATUS_PENDING,
                )
            )

    def update(self, current_game_seconds, is_in_game):
        current_game_second = int(current_game_seconds)
        if current_game_second == self._last_processed_game_second:
            return

        self._last_processed_game_second = current_game_second

        for wave in self._wave_states:
            if wave.status in (self.STATUS_COMPLETED, self.STATUS_CANCELLED_BY_NEXT_PHASE):
                continue

            seconds_until_wave = wave.target_game_second - current_game_second

            if seconds_until_wave <= 0:
                self._remove_alert(wave.alert_id)
                wave.status = self.STATUS_COMPLETED
                continue

            if seconds_until_wave <= self.ALERT_LEAD_SECONDS:
                wave.status = self.STATUS_ALERTING
                message = self._build_message(seconds_until_wave, wave.army_strength)
                self.toast_manager.show_map_countdown_alert(
                    wave.alert_id,
                    seconds_until_wave,
                    message,
                    is_in_game,
                )

    def reset(self):
        self.clear_all_alerts()
        self._wave_states.clear()
        self._current_phase = None
        self._last_processed_game_second = None

    def clear_all_alerts(self):
        for wave in self._wave_states:
            self._remove_alert(wave.alert_id)

    def get_wave_states(self):
        return [asdict(wave) for wave in self._wave_states]

    def _cancel_unfinished_previous_phase_waves(self, new_phase):
        for wave in self._wave_states:
            if wave.phase == new_phase:
                continue

            if wave.status == self.STATUS_PENDING:
                wave.status = self.STATUS_CANCELLED_BY_NEXT_PHASE
            elif wave.status == self.STATUS_ALERTING:
                self._remove_alert(wave.alert_id)
                wave.status = self.STATUS_CANCELLED_BY_NEXT_PHASE

    def _remove_alert(self, alert_id):
        if hasattr(self.toast_manager, "has_alert") and not self.toast_manager.has_alert(alert_id):
            return

        self.toast_manager.remove_alert(alert_id)

    def _build_alert_id(self, phase, wave_index):
        return f"cradle_of_death_phase_{phase}_wave_{wave_index}"

    def _build_message(self, seconds_until_wave, army_strength):
        return f"{seconds_until_wave}秒后  {self.EVENT_NAME}    {army_strength}"

    def _log_debug(self, message):
        if self.logger and hasattr(self.logger, "debug"):
            self.logger.debug(message)
