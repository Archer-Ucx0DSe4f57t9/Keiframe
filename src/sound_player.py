# sound_player.py
import os
import time
import logging
from typing import List, Optional


from PyQt5.QtCore import QObject, QUrl
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
import config

logger = logging.getLogger(__name__)


class SoundManager(QObject):
    """
    用 PyQt5.QtMultimedia.QMediaPlayer 播放音频（支持 mp3/ogg/wav，取决于 Qt 后端）。
    - search_paths: 可选的音频搜索目录列表（会按顺序查找第一个匹配的文件）
    - cooldown_seconds: 同名文件播放的冷却时间（默认 10s）
    - volume: 0.0 - 1.0
    """
    def __init__(self, search_paths: Optional[List[str]] = None,
                 cooldown_seconds: float = 10.0, volume: float = 0.9, parent=None):
        super().__init__(parent)
        self.cooldown_seconds = float(config.ALERT_SOUND_COOLDOWN)
        self.volume = float(max(config.ALERT_SOUND_VOLUME / 100, 1.0))
        self._last_played = {}   # filename -> last play timestamp (float)
        self._players = {}       # filename -> QMediaPlayer (cached)
        self.search_paths = list(search_paths) if search_paths else self._default_search_paths()

    def _default_search_paths(self) -> List[str]:
        """
        默认搜索路径（按顺序）：
          1) 上级目录的 Sounds（相对于本模块文件）
          2) 项目资源目录下的 Sounds （如果有 fileutil.get_resources_dir）
          3) 当前工作目录的 Sounds
        """
        paths = []
        # 1) 上级目录的 Sounds
        try:
            base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'resources', 'sounds'))
            paths.append(base)
        except Exception:
            pass

        # 2) 如果项目有 fileutil.get_resources_dir，尝试使用
        try:
            from fileutil import get_resources_dir
            paths.append(os.path.join(get_resources_dir(), 'sounds'))
        except Exception:
            pass

        # 3) 当前工作目录的 Sounds
        paths.append(os.path.join(os.getcwd(), 'sounds'))

        # 还可以按需在此处添加更多路径
        return paths

    def find_sound_file(self, filename: str) -> Optional[str]:
        """在 self.search_paths 中按顺序寻找 filename，返回绝对路径或 None。"""
        if not filename:
            return None
        for d in self.search_paths:
            if not d:
                continue
            p = os.path.join(d, filename)
            print(p)
            if os.path.isfile(p):
                return os.path.abspath(p)
        return None

    def play(self, filename: str, force: bool = False) -> bool:
        """
        尝试播放 filename（可为 mp3）。如果同名文件在 cooldown 内已播放过，则返回 False（未播放）。
        返回 True 表示已触发播放请求（非阻塞）。
        """
        if not filename:
            return False

        now = time.time()
        last = self._last_played.get(filename)
        if not force and last is not None and (now - last) < self.cooldown_seconds:
            # 在冷却期内，跳过播放
            logger.debug("SoundManager: skipped '%s' (cooldown)", filename)
            return False

        path = self.find_sound_file(filename)
        if not path:
            logger.warning("SoundManager: sound file not found: %s", filename)
            return False

        try:
            player = self._players.get(filename)
            if player is None:
                player = QMediaPlayer(self)
                # QMediaPlayer volume 是 0-100（整数）
                try:
                    player.setVolume(int(self.volume * 100))
                except Exception:
                    # 有些 Qt 版本/平台可能不同，容错处理
                    pass

                # 可选：当播放完成时我们可以选择清理播放器，也可以缓存以便重用
                # player.mediaStatusChanged.connect(lambda status, fn=filename: self._on_media_status(status, fn))

                self._players[filename] = player

            # setMedia + play
            # PyQt5 支持 QMediaContent(QUrl.fromLocalFile(path))
            player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
            player.play()

            self._last_played[filename] = now
            logger.debug("SoundManager: playing '%s' -> %s", filename, path)
            return True
        except Exception as e:
            logger.exception("SoundManager: failed to play %s: %s", filename, e)
            return False

    def _on_media_status(self, status, filename):
        # 目前我们不做主动清理；如果希望在播放完成后释放内存可在此实现
        from PyQt5.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.EndOfMedia:
            # 如果不想缓存播放器，可以停止并删除：
            # p = self._players.pop(filename, None)
            # if p: p.stop(); p.deleteLater()
            pass

    # 可选：手动清理缓存播放器
    def clear_cache(self):
        for p in list(self._players.values()):
            try:
                p.stop()
                p.deleteLater()
            except Exception:
                pass
        self._players.clear()
        self._last_played.clear()

shared_sound_manager = SoundManager()