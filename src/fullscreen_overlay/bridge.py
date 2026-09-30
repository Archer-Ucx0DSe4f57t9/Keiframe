import hashlib
import os
import queue
import threading
import time
from pathlib import Path

from PyQt5.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QTimer
from PyQt5.QtGui import QColor, QImage, QPainter, QRegion
from PyQt5.QtWidgets import QApplication, QWidget

from src.fullscreen_overlay.layout import select_capture_geometry
from src.fullscreen_overlay.protocol import encode_frame
from src.utils.logging_util import get_logger
from src.utils.window_utils import get_sc2_window_geometry, is_sc2_fullscreen


logger = get_logger(__name__)

GAMEBAR_PACKAGE_FAMILY = "Keiframe.GameBar_83kdtmzvrsrdt"
MAILBOX_FILE_NAME = "overlay.frame"
COMMAND_FILE_NAME = "overlay.command"
CONTENT_MARGIN = 8


class _FrameMailbox:
    """Atomically publish the latest frame in the widget's LocalState folder."""

    def __init__(self):
        local_app_data = os.environ.get("LOCALAPPDATA")
        self._folder = (
            Path(local_app_data)
            / "Packages"
            / GAMEBAR_PACKAGE_FAMILY
            / "LocalState"
            if local_app_data
            else None
        )
        self._frames = queue.Queue(maxsize=1)
        self._stopping = threading.Event()
        self._thread = None
        self._warned = False

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run,
            name="KeiframeGameBarMailbox",
            daemon=True,
        )
        self._thread.start()

    def publish(self, payload: bytes):
        try:
            self._frames.put_nowait(payload)
        except queue.Full:
            try:
                self._frames.get_nowait()
            except queue.Empty:
                pass
            try:
                self._frames.put_nowait(payload)
            except queue.Full:
                pass

    def stop(self):
        self._stopping.set()

    def consume_command(self):
        """Return and remove one command written by the Game Bar widget."""
        if self._folder is None:
            return None

        target = self._folder / COMMAND_FILE_NAME
        try:
            command = target.read_text(encoding="utf-8").strip()
            target.unlink(missing_ok=True)
            return command or None
        except FileNotFoundError:
            return None
        except Exception as exc:
            logger.warning(f"无法读取 Game Bar 控制命令: {exc}")
            return None

    def _run(self):
        if self._folder is None:
            logger.warning("LOCALAPPDATA 未设置，无法启动 Game Bar 画面邮箱")
            return

        target = self._folder / MAILBOX_FILE_NAME
        temporary = self._folder / f"{MAILBOX_FILE_NAME}.tmp"
        while not self._stopping.is_set():
            try:
                payload = self._frames.get(timeout=0.25)
            except queue.Empty:
                continue

            try:
                self._folder.mkdir(parents=True, exist_ok=True)
                with temporary.open("wb") as stream:
                    stream.write(payload)
                    stream.flush()
                os.replace(temporary, target)
                self._warned = False
            except Exception as exc:
                if not self._warned:
                    logger.warning(f"无法更新 Game Bar 画面邮箱: {exc}")
                    self._warned = True


class FullscreenOverlayBridge:
    """
    Mirror Keiframe's visible Qt windows into one transparent Game Bar widget.

    The existing widgets remain the single source of truth.  Only the bounding
    box containing visible Keiframe content is sent to Game Bar.  Keeping the
    Game Bar widget compact leaves its title bar and close controls reachable
    and prevents a transparent full-screen surface from swallowing game input.
    """

    def __init__(self, owner):
        self.owner = owner
        self._mailbox = _FrameMailbox()
        self._last_digest = None
        self._last_payload = None
        self._last_publish_at = 0.0
        self._sequence = 0
        self._timer = QTimer(owner)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._publish_if_changed)

    def start(self):
        self._mailbox.start()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self._mailbox.stop()

    def _publish_if_changed(self):
        self._consume_widget_command()

        if not is_sc2_fullscreen():
            return

        viewport = get_sc2_window_geometry()
        if not viewport:
            return
        _, _, viewport_width, viewport_height = viewport
        if viewport_width <= 0 or viewport_height <= 0:
            return

        owner_geometry = None
        owner_screen_geometry = None
        if self.owner is not None and self.owner.isVisible():
            owner_frame = self.owner.frameGeometry()
            owner_geometry = (
                owner_frame.x(),
                owner_frame.y(),
                owner_frame.width(),
                owner_frame.height(),
            )
            owner_screen = None
            window_handle = self.owner.windowHandle()
            if window_handle is not None:
                owner_screen = window_handle.screen()
            if owner_screen is None:
                owner_center = owner_frame.center()
                owner_screen = next(
                    (
                        screen
                        for screen in QApplication.screens()
                        if screen.geometry().contains(owner_center)
                    ),
                    None,
                )
            if owner_screen is not None:
                screen_geometry = owner_screen.geometry()
                owner_screen_geometry = (
                    screen_geometry.x(),
                    screen_geometry.y(),
                    screen_geometry.width(),
                    screen_geometry.height(),
                )

        (
            capture_x,
            capture_y,
            capture_width,
            capture_height,
        ) = select_capture_geometry(
            viewport,
            owner_geometry,
            owner_screen_geometry,
        )

        visible_widgets = []
        for widget in QApplication.topLevelWidgets():
            if (
                widget is None
                or not widget.isVisible()
                or widget.width() <= 0
                or widget.height() <= 0
                or widget.windowOpacity() <= 0.001
            ):
                continue

            frame = widget.frameGeometry()
            relative_x = frame.x() - capture_x
            relative_y = frame.y() - capture_y
            clipped_left = max(0, relative_x)
            clipped_top = max(0, relative_y)
            clipped_right = min(
                capture_width,
                relative_x + frame.width(),
            )
            clipped_bottom = min(
                capture_height,
                relative_y + frame.height(),
            )
            if clipped_left >= clipped_right or clipped_top >= clipped_bottom:
                continue
            visible_widgets.append(
                (
                    widget,
                    relative_x,
                    relative_y,
                    clipped_left,
                    clipped_top,
                    clipped_right,
                    clipped_bottom,
                )
            )

        if visible_widgets:
            content_left = max(
                0,
                min(item[3] for item in visible_widgets) - CONTENT_MARGIN,
            )
            content_top = max(
                0,
                min(item[4] for item in visible_widgets) - CONTENT_MARGIN,
            )
            content_right = min(
                capture_width,
                max(item[5] for item in visible_widgets) + CONTENT_MARGIN,
            )
            content_bottom = min(
                capture_height,
                max(item[6] for item in visible_widgets) + CONTENT_MARGIN,
            )
        else:
            content_left = 0
            content_top = 0
            content_right = 1
            content_bottom = 1

        content_width = max(1, content_right - content_left)
        content_height = max(1, content_bottom - content_top)
        canvas = QImage(
            content_width,
            content_height,
            QImage.Format_ARGB32_Premultiplied,
        )
        canvas.fill(QColor(0, 0, 0, 0))

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        try:
            for widget, relative_x, relative_y, *_ in visible_widgets:
                painter.save()
                painter.setOpacity(widget.windowOpacity())
                widget.render(
                    painter,
                    QPoint(
                        relative_x - content_left,
                        relative_y - content_top,
                    ),
                    QRegion(),
                    QWidget.DrawChildren,
                )
                painter.restore()
        finally:
            painter.end()

        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.WriteOnly)
        canvas.save(buffer, "PNG")
        png_bytes = bytes(byte_array)
        frame_signature = (
            f"{capture_x}:{capture_y}:"
            f"{capture_width}:{capture_height}:"
            f"{content_left}:{content_top}:"
            f"{content_width}:{content_height}:"
        ).encode("ascii")
        digest = hashlib.sha1(frame_signature + png_bytes).digest()
        now = time.monotonic()
        if digest == self._last_digest:
            # Re-send the last frame periodically so a newly activated widget
            # can populate itself even when the visible overlay is unchanged.
            if (
                self._last_payload is not None
                and now - self._last_publish_at >= 1.0
            ):
                self._mailbox.publish(self._last_payload)
                self._last_publish_at = now
            return

        self._last_digest = digest
        self._sequence += 1
        payload = encode_frame(
            {
                "sequence": self._sequence,
                "width": content_width,
                "height": content_height,
                "source_width": capture_width,
                "source_height": capture_height,
                "origin_x": content_left,
                "origin_y": content_top,
            },
            png_bytes,
        )
        self._last_payload = payload
        self._last_publish_at = now
        self._mailbox.publish(payload)

    def _consume_widget_command(self):
        command = self._mailbox.consume_command()
        if not command:
            return

        command_name = command.splitlines()[0].strip().casefold()
        if command_name == "toggle_lock":
            lock_signal = getattr(self.owner, "lock_signal", None)
            if lock_signal is not None:
                lock_signal.emit()
                logger.info("已执行 Game Bar 小组件的锁定切换命令")
            return

        logger.warning(f"忽略未知的 Game Bar 控制命令: {command_name}")
