import os
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QFont, QPixmap, QPainter, QPen, QColor, QFontMetrics
from PyQt5.QtWidgets import QLabel, QHBoxLayout

from src.utils.fileutil import get_resources_dir
import sys
from src import config

from src.output.sound_player import shared_sound_manager

# 将屏幕提示优化，减少帧数影响
class OutlinedLabel(QLabel):
    def __init__(self, outline_color='black', parent=None):
        super().__init__(parent)
        self._outline_color = QColor(outline_color)
        self._outline_width = 1
        self._font = QFont('Arial', 16)
        self._cached_pixmap = None
        self._cached_props = (None, None, None)  # (text, font.pointSize(), outline_width)

    def setFont(self, font):
        super().setFont(font)
        self._font = font
        self._invalidate_cache_and_update()

    def setFontSize(self, font_size):
        f = QFont(self._font)
        f.setPointSize(font_size)
        self.setFont(f)

    def setOutlineWidth(self, width):
        self._outline_width = max(1, int(width))
        self._invalidate_cache_and_update()

    def setOutlineColor(self, color):
        self._outline_color = QColor(color)
        self._invalidate_cache_and_update()

    def setText(self, text):
        super().setText(text)
        self._invalidate_cache_and_update()

    def _invalidate_cache_and_update(self):
        self._cached_pixmap = None
        self.update()

    def set_font_pixel_size(self, px: int):
        """显式以像素为单位设置字体大小（立即生效）。"""
        if px <= 0:
            return
        f = QFont(self.font())  # 以当前 font 为基础
        # 使用 setPixelSize 确保像素精确度（比 setPointSize 更直观）
        f.setPixelSize(int(px))
        super().setFont(f)
        # 使渲染缓存失效
        self._cached_pixmap = None

    def fit_font_to_line_height(self, line_height: int, text_fraction: float = 0.6, min_px=6, max_px=200):
        """
        给定期望行高（像素）和 text_fraction（文本占行高比例），自动找到一个像素字体大小，
        使 fm.height() 接近 desired_text_h = line_height * text_fraction。

        使用二分法快速收敛。成功后会调用 set_font_pixel_size 找到的 px。
        """
        if line_height <= 0:
            return
        desired_text_h = max(1, int(line_height * float(text_fraction)))
        lo, hi = min_px, max_px
        best_px = lo
        best_diff = None
        while lo <= hi:
            mid = (lo + hi) // 2
            f = QFont(self.font())
            f.setPixelSize(mid)
            fm = QFontMetrics(f)
            h = fm.height()
            diff = h - desired_text_h
            if best_diff is None or abs(diff) < best_diff:
                best_diff = abs(diff)
                best_px = mid
                if best_diff == 0:
                    break
            if h > desired_text_h:
                hi = mid - 1
            else:
                lo = mid + 1
        # 应用找到的像素大小
        self.set_font_pixel_size(best_px)
        # 清缓存
        self._cached_pixmap = None

    def set_line_height(self, line_height: int):
        """
        告诉 label 期望的行高（像素）。在 _render_to_pixmap 中会使 pixmap 高度至少为 line_height，
        并将文字在该高度内垂直居中（避免裁切或过多空白）。
        """
        if line_height is None:
            self._line_height = None
        else:
            self._line_height = max(1, int(line_height))
        self._cached_pixmap = None

    def _render_to_pixmap(self):
        """
        渲染文本到缓存 pixmap。若 self._line_height 被设置，则确保 pixmap.height >= line_height，
        并把文本垂直居中（通过 baseline 精确定位）。
        """
        text = super().text() or ""
        if not text:
            self._cached_pixmap = QPixmap()
            return

        font = self.font()
        fm = QFontMetrics(font)
        br = fm.boundingRect(text)
        text_w = fm.horizontalAdvance(text)
        ascent = fm.ascent()
        descent = fm.descent()
        text_h = ascent + descent  # 或用 br.height()

        # 参数（可调）
        shadow_offsets = [(3, 3), (2, 2), (1, 1)]
        shadow_color = QColor(0, 0, 0, 200)
        outline_w = max(1, int(getattr(self, '_outline_width', 1)))

        # 为 outline/shadow 留出最小空间（尽量精简）
        max_offset = max((abs(dx) + abs(dy) for dx, dy in shadow_offsets), default=0)
        min_pad_for_effects = outline_w + max_offset
        padding_left = max(2, min_pad_for_effects)
        padding_right = max(2, min_pad_for_effects)
        padding_top = max(2, min_pad_for_effects)
        padding_bottom = max(2, min_pad_for_effects)

        # 计算最小 pixmap 尺寸
        min_w = max(1, text_w + padding_left + padding_right)
        min_h = max(1, text_h + padding_top + padding_bottom)

        # 如果外部指定了 line_height（期望的整行高度），以此为最小高度并垂直居中
        h = min_h
        if getattr(self, '_line_height', None):
            h = max(min_h, int(self._line_height))

        w = min_w

        pix = QPixmap(w, h)
        pix.fill(Qt.transparent)

        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setFont(font)

        # baseline_y：在高度 h 内垂直居中：baseline = (h - text_h)//2 + ascent
        baseline_y = (h - text_h) // 2 + ascent
        x0 = padding_left

        # 1) 阴影
        if shadow_offsets:
            pen = QPen(shadow_color)
            pen.setWidth(outline_w * 2)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            for dx, dy in shadow_offsets:
                painter.drawText(x0 + dx, baseline_y + dy, text)

        # 2) 描边
        pen = QPen(getattr(self, '_outline_color', QColor(0, 0, 0)))
        pen.setWidth(outline_w * 2)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawText(x0, baseline_y, text)

        # 3) 正文
        fg = self.palette().color(self.foregroundRole())
        painter.setPen(fg)
        painter.drawText(x0, baseline_y, text)

        painter.end()

        # 缓存并设置控件大小（水平保持文本宽度，垂直使用 h）
        self._cached_pixmap = pix
        # 保持宽度为 pix.width()，高度为 h（这样外层布局期望的 line_height 可被满足）
        self.setFixedSize(pix.size())

    def paintEvent(self, event):
        if self._cached_pixmap is None:
            self._render_to_pixmap()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        if self._cached_pixmap and not self._cached_pixmap.isNull():
            painter.drawPixmap(0, 0, self._cached_pixmap)
        painter.end()

# 负责将输入的文本消息转换成屏幕消息，如果有提示语音也播放。
class MessagePresenter(QLabel):
    def __init__(self, parent=None, icon_name=None):
        super().__init__(parent)
        self.hide()

        self._last_message = None
        self._last_color = None
        self.icon_name = icon_name
        self._last_render_time = 0.0
        self._throttle_seconds = 0.08  # 节流（可调整到 0.08~0.2s）

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # icon
        self.icon_label = None
        if icon_name:
            self.icon_label = QLabel()
            layout.addWidget(self.icon_label)

        # text (我们的缓存 label)
        self.text_label = OutlinedLabel(outline_color='black')
        self.text_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.text_label.setOutlineWidth(2)
        self.text_label.setAlignment(Qt.AlignVCenter)
        layout.addWidget(self.text_label)

        # 一次性设置 flags/attributes（不要在 show 时重复 setWindowFlags）
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        if self.icon_label:
            self.icon_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        if sys.platform.startswith("win"):
            from PyQt5 import sip
            import win32gui, win32con

            hwnd = self.winId()  # 获取窗口句柄
            # 当前扩展样式
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            # 加上 WS_EX_TRANSPARENT 和 WS_EX_LAYERED
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                                   ex_style | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_LAYERED)

    def update_message(self, message, color, x=None, y=None, width=None, height=None, font_size=16, sound_filename:str = None):

        # 仅在发生变化时设置 text / style（OutlinedLabel 会缓存渲染）
        if message != self._last_message or color != self._last_color:
            if height is not None:
                self.text_label.set_line_height(int(height))
            self.text_label.set_font_pixel_size(int(font_size))  # 用像素字体
            self.text_label.setText(message)
            # 通过 palette 或 stylesheet 设置前景色（这里用 setStyleSheet）
            self.text_label.setStyleSheet(f'color: {color}; background-color: transparent;')
            self._last_message = message
            self._last_color = color

        if self.icon_label and self.icon_name:
            icon_path = os.path.join(get_resources_dir(), 'ico', 'mutator', self.icon_name)
            if os.path.exists(icon_path):
                px = QPixmap(icon_path).scaled(font_size, font_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.icon_label.setPixmap(px)

        if x is not None and y is not None:
            if width and height:
                # 仅在尺寸变化时调用 setFixedSize（避免频繁布局重算）
                if self.width() != width or self.height() != height:
                    self.setFixedSize(width, height)
            self.move(x, y)

        if sound_filename is not None:
            shared_sound_manager.play(sound_filename)

        if not self.isVisible():
            self.show()



    def hide_alert(self):
        self.hide()

    # 以下3保证点击穿透
    def mousePressEvent(self, event):
        event.ignore()

    def mouseReleaseEvent(self, event):
        event.ignore()

    def mouseMoveEvent(self, event):
        event.ignore()