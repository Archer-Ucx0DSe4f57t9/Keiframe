import os
import sys
from PyQt5.QtWidgets import QWidget, QLabel, QApplication
from PyQt5.QtCore import Qt, QPropertyAnimation, QRect, QTimer, QEasingCurve, QSequentialAnimationGroup, QPauseAnimation
from PyQt5.QtGui import QPixmap, QColor
import win32gui
import win32con

import config
import window_utils
from logging_util import get_logger

logger = get_logger('memo_overlay')

class MemoOverlay(QWidget):
    
    # ... (set_click_through 保持不变) ...
    # ... (hide_memo 保持不变) ...

    def __init__(self, titles=["StarCraft II", "《星际争霸II》"]): # 保持与原始代码一致，但不需要 titles
        super().__init__() 
        
        # 基础窗口属性设置
        self.setWindowFlags(
            Qt.FramelessWindowHint |       # 无边框
            Qt.WindowStaysOnTopHint |      # 总是置顶
            Qt.Tool |                      # 工具窗口，不在任务栏显示
            Qt.WindowTransparentForInput   # 关键：QT层面的点击穿透 (Qt 5.10+)
        )
        
        # 启用背景透明，这是实现半透明窗口的基础
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating) # 显示时不抢焦点
        
        # 1. 背景图片容器 (用于全屏半透明黑色背景)
        self.background_label = QLabel(self)
        self.background_label.setAlignment(Qt.AlignCenter)
        self.background_label.setStyleSheet("background-color: transparent;") # 确保它不影响 MemoOverlay 窗口本身的样式
        
        # 2. Memo 图片容器 (放在背景上方，居中显示)
        self.memo_label = QLabel(self)
        self.memo_label.setAlignment(Qt.AlignCenter)
        self.memo_label.setStyleSheet("background-color: transparent;") # 图片下方的背景由 background_label 提供
        
        # 注意：不再使用 MemoOverlay 窗口本身的样式表来绘制背景

        # 动画组 (用于临时显示的停留+淡出)
        self.anim_group = QSequentialAnimationGroup(self)
        
        # 初始化透明度
        self.target_opacity = getattr(config, 'MEMO_OPACITY', 0.7)
        self.duration = getattr(config, 'MEMO_DURATION', 5000)
        self.fade_time = getattr(config, 'MEMO_FADE_TIME', 1000)
        
        self.setWindowOpacity(0) # 初始隐藏
        
        # 强制 Win32 API 穿透
        self.set_click_through()

    def set_click_through(self):
        """设置 Windows 扩展样式以实现完全的鼠标穿透"""
        try:
            hwnd = self.winId()
            styles = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            # 必须设置 WS_EX_LAYERED 才能使 setWindowOpacity() 和 WS_EX_TRANSPARENT 同时生效
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, styles | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_LAYERED)
        except Exception as e:
            logger.error(f"设置点击穿透失败: {e}")

    def load_and_show(self, map_name, mode='temp'):
        """
        显示 Memo
        """
        # 1. 检查是否是 toggle 模式且当前正在显示，如果是则关闭
        if mode == 'toggle' and self.isVisible() and self.windowOpacity() > 0.01:
            self.hide_memo()
            return

        # 2. 获取图片路径
        memo_image_path = os.path.join(os.getcwd(), 'memo', f'{map_name}.png')
        bg_image_path = os.path.join(os.getcwd(), 'memo', 'background.png')
        
        if not os.path.exists(memo_image_path):
            logger.warning(f"Memo图片不存在: {memo_image_path}")
            return
        if not os.path.exists(bg_image_path):
            logger.error(f"背景图片不存在，请在 memo 文件夹中放入半透明的 background.png: {bg_image_path}")
            return

        # 3. 获取游戏窗口几何信息
        geo = window_utils.get_sc2_window_geometry()
        if not geo:
            logger.warning("无法获取星际2窗口位置")
            return
        
        sc2_x, sc2_y, sc2_w, sc2_h = geo

        # --- A. 设置背景图 ---
        bg_pixmap = QPixmap(bg_image_path)
        # 缩放到游戏窗口大小
        scaled_bg_pixmap = bg_pixmap.scaled(sc2_w, sc2_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self.background_label.setPixmap(scaled_bg_pixmap)
        self.background_label.resize(sc2_w, sc2_h)
        self.background_label.move(0, 0)
        
        # MemoOverlay 窗口尺寸设置为游戏窗口尺寸
        self.resize(sc2_w, sc2_h)

        # --- B. 加载并处理 Memo 图片 ---
        memo_pixmap = QPixmap(memo_image_path)
        img_w = memo_pixmap.width()
        img_h = memo_pixmap.height()

        # 计算 Memo 图片缩放 (只在大于 SC2 窗口时缩小)
        scale_ratio = 1.0
        new_w = img_w
        new_h = img_h
        
        if img_w > sc2_w or img_h > sc2_h:
            scale_ratio = min(sc2_w / img_w, sc2_h / img_h)
            
            if scale_ratio < 1.0:
                new_w = int(img_w * scale_ratio)
                new_h = int(img_h * scale_ratio)
                memo_pixmap = memo_pixmap.scaled(new_w, new_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                logger.info(f"Memo 图片已缩放至: {new_w}x{new_h}")
        
        self.memo_label.setPixmap(memo_pixmap)
        self.memo_label.resize(new_w, new_h)
        
        # --- C. Memo 图片居中 ---
        # Memo 图片相对于 MemoOverlay 窗口居中
        memo_x = (sc2_w - new_w) // 2
        memo_y = (sc2_h - new_h) // 2
        self.memo_label.move(memo_x, memo_y)
        

        # --- D. MemoOverlay 窗口定位 ---
        # MemoOverlay 窗口移动到 SC2 窗口位置
        self.move(int(sc2_x), int(sc2_y))

        # 6. 显示逻辑
        self.show() # 必须先show才能设置透明度
        
        # 停止之前的动画
        if self.anim_group.state() == QSequentialAnimationGroup.Running:
            self.anim_group.stop()

        if mode == 'temp':
            self.start_temp_animation()
        elif mode == 'toggle':
            self.setWindowOpacity(self.target_opacity)
            logger.info("Memo 持续显示模式开启")

    def start_temp_animation(self):
        """执行：显示 -> 等待 -> 淡出 -> 隐藏"""
        self.anim_group.clear()
        
        # 瞬间设置到目标透明度
        self.setWindowOpacity(self.target_opacity)
        
        # 1. 停留阶段 (PauseAnimation)
        pause = QPauseAnimation(self.duration)
        
        # 2. 淡出阶段 (PropertyAnimation)
        fade_out = QPropertyAnimation(self, b"windowOpacity")
        fade_out.setDuration(self.fade_time)
        fade_out.setStartValue(self.target_opacity)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Linear)
        
        self.anim_group.addAnimation(pause)
        self.anim_group.addAnimation(fade_out)
        
        # 动画结束后真正隐藏窗口
        self.anim_group.finished.connect(self.hide)
        self.anim_group.start()
        logger.info(f"Memo 临时显示: {self.duration}ms 后消失")

    def hide_memo(self):
        """强制隐藏"""
        self.anim_group.stop()
        self.setWindowOpacity(0)
        self.hide()
        logger.info("Memo 已隐藏")