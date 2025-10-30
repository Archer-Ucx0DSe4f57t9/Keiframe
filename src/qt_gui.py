import os
import sys
import traceback
import threading, asyncio
from PyQt5.QtWidgets import (QMainWindow, QApplication)
from control_window import ControlWindow
from PyQt5.QtCore import Qt, QTimer, QPoint, pyqtSignal
import config
from PyQt5 import QtCore

import image_util
from toast_manager import ToastManager
import ui_setup, game_monitor, config_hotkeys,game_time_handler,map_loader,app_window_manager,language_manager


class TimerWindow(QMainWindow):
    # 创建信号用于地图更新
    progress_signal = QtCore.pyqtSignal(list)
    toggle_artifact_signal = pyqtSignal()

    def get_screen_resolution(self):
        return app_window_manager.get_screen_resolution()

    def _run_async_game_scheduler(self, progress_signal):
        """在新线程中启动 asyncio 事件循环"""
        asyncio.run(game_monitor.check_for_new_game_scheduler(progress_signal))

    def __init__(self):
        super().__init__()
        #在最开始安全地初始化 control_window 为 None
        # 万一在真正创建前触发了 moveEvent，它可以通过 hasattr() 或 try/except 优雅地失败。
        self.control_window = None

        # 初始化artifact_window
        from misc.artifacts import ArtifactWindow
        self.artifact_window = ArtifactWindow(self)

        # 设置窗口属性以支持DPI缩放
        self.setAttribute(Qt.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WA_NativeWindow)
        if getattr(sys, 'frozen', False):  # 是否为打包的 exe
            base_dir = os.path.dirname(sys.executable)  # exe 所在目录
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 源码所在目录

        # 初始化日志记录器
        from logging_util import get_logger
        self.logger = get_logger(__name__)
        self.logger.info('SC2 Timer 启动')

        # 初始化状态
        self.current_time = ""
        self.drag_position = QPoint(0, 0)
        self.game_state = game_monitor.state

        # 添加一个标志来追踪地图选择的来源
        self.manual_map_selection = False

        #初始化地图管理模块
        self.toast_manager = ToastManager(self)
        self.map_event_manager = None
        self.is_map_Malwarfare = False
        self.malwarfare_handler = None
        
        # 初始化UI
        self.init_ui()

        # 初始化定时器
        self.timer = QTimer()
        self.timer.timeout.connect(lambda: game_time_handler.update_game_time(self))
        self.timer.start(200)  # 自动开始更新，每200毫秒更新一次

        # 连接表格区域的双击事件
        self.table_area.mouseDoubleClickEvent = self.on_text_double_click

        # 初始化系统托盘
        self.init_tray()

        # 搜索框的信号连接
        if hasattr(self, 'files'): # 确保 setup_search_and_combo_box 已创建 files
            self.setup_search_box_connections(self.files)
            
        # 初始化全局快捷键
        config_hotkeys.init_global_hotkeys(self)
        
         # 启动游戏检查线程
        self.game_check_thread = threading.Thread(target=self._run_async_game_scheduler, args=(self.progress_signal,), daemon=True)
        self.game_check_thread.start()
        

        # 创建控制窗体
        self.control_window = ControlWindow()
        self.control_window.move(self.x(), self.y() - self.control_window.height())
   
        # 连接控制窗口的状态改变信号
        self.control_window.state_changed.connect(lambda unlocked: app_window_manager.on_control_state_changed(self,unlocked))

        # 监听主窗口位置变化
        self.windowHandle().windowStateChanged.connect(lambda: app_window_manager.update_control_window_position(self))

        # 连接信号到处理函数
        self.progress_signal.connect(self.handle_progress_update)

        QTimer.singleShot(50, self.show_control_window)
        # 强制加载第一个地图
        if hasattr(self, 'files') and self.files:
            map_loader.handle_map_selection(self, self.files[0])

        # 显示窗口并强制置顶
        self.show()
        if sys.platform == 'win32':
            import win32gui
            import win32con
            hwnd = int(self.winId())
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)

        # 初始化时设置为锁定状态（不可点击）
        # 使用延迟调用，确保窗口已完全初始化
        QTimer.singleShot(100, lambda: app_window_manager.on_control_state_changed(self, False))

    def get_current_screen(self):
        """获取当前窗口所在的显示器"""
        window_geometry = self.geometry()
        window_center = window_geometry.center()

        # 获取所有显示器
        screens = QApplication.screens()

        # 遍历所有显示器，检查窗口中心点是否在显示器范围内
        for screen in screens:
            screen_geometry = screen.geometry()
            if screen_geometry.contains(window_center):
                return screen

        # 如果没有找到，返回主显示器
        return QApplication.primaryScreen()

    def show_control_window(self):
        """辅助方法：确保 control_window 存在后才显示和定位"""
        if self.control_window:
            # 注意：调用 app_window_manager 模块中的函数进行位置更新
            app_window_manager.update_control_window_position(self)
            self.control_window.show()

    def moveEvent(self, event):
        """鼠标移动事件，用于更新控制窗口位置"""
        app_window_manager.update_control_window_position(self)
        super().moveEvent(event)

    def handle_screenshot_hotkey(self):
        """处理截图快捷键"""
        if not config.DEBUG_SHOW_ENEMY_INFO_SQUARE:
            return

        try:
            # 使用已保存的矩形区域进行截图
            successful_captures = 0

            for rect in self.rect_screenshots:
                try:
                    # 调用capture_screen_rect进行截图并保存
                    save_path = image_util.capture_screen_rect(rect)
                    if save_path:
                        self.logger.info(f'成功保存截图到: {save_path}')
                        successful_captures += 1
                    else:
                        self.logger.warning(f'截图保存失败: {rect.x()}, {rect.y()}, {rect.width()}, {rect.height()}')
                except Exception as capture_error:
                    self.logger.error(f'区域截图失败: {str(capture_error)}')
                    self.logger.error(traceback.format_exc())

            if successful_captures == len(self.rect_screenshots):
                self.logger.info('所有区域截图完成')
            else:
                self.logger.warning(f'部分区域截图失败: 成功{successful_captures}/{len(self.rect_screenshots)}')
        except Exception as e:
            self.logger.error(f'截图处理失败: {str(e)}')
            self.logger.error(traceback.format_exc())

    def init_ui(self):
        ui_setup.init_ui(self)
        
    

    def setup_search_box_connections(self, files):
        ####################
        # 用户输入搜索
        # 清空搜索框的定时器->现在在ui_setup实现
        #self.clear_search_timer = QTimer()
        #self.clear_search_timer.setSingleShot(True)

        # 更新搜索内容
        def update_combo_box(keyword, allow_auto_select=True):

            keyword = keyword.strip().lower()
            current_selected = self.combo_box.currentText()

            self.combo_box.blockSignals(True)  # 🚫 禁止选项变化触发 currentTextChanged
            self.combo_box.clear()

            filtered = [f for f in files if keyword in f.lower()]

            mapped_result = config.MAP_SEARCH_KEYWORDS.get(keyword)
            if mapped_result and mapped_result not in filtered and mapped_result in files:
                filtered.insert(0, mapped_result)

            self.combo_box.addItems(filtered)

            # ✅ 如果不是自动选择场景，恢复原选项
            if not allow_auto_select and current_selected in filtered:
                index = self.combo_box.findText(current_selected)
                if index >= 0:
                    self.combo_box.setCurrentIndex(index)

            self.combo_box.blockSignals(False)

            # ✅ 只在明确需要时触发地图变更
            if filtered and allow_auto_select:
                map_loader.handle_map_selection(self, filtered[0])

        # 用户输入时触发（允许自动选择）
        def filter_combo_box_user():
            keyword = self.search_box.text().strip().lower()
            update_combo_box(keyword, allow_auto_select=True)

        # 自动清除时触发（禁止自动选择）
        def filter_combo_box_clear():
            update_combo_box("", allow_auto_select=False)
            self.search_box.blockSignals(True)
            self.search_box.setText("")  # 不触发 filter_combo_box_user
            self.search_box.blockSignals(False)

        # 根据搜索更新可选列表
        def restart_clear_timer():
            self.clear_search_timer.stop()
            self.clear_search_timer.start(30000)  # 30秒

        # 搜索框关联
        self.search_box.textChanged.connect(filter_combo_box_user)
        self.search_box.textChanged.connect(restart_clear_timer)
        self.clear_search_timer.timeout.connect(filter_combo_box_clear)
        self.combo_box.currentTextChanged.connect(self.on_map_selected)

        # 调整时间标签的位置和高度
        self.time_label.setGeometry(10, 40, 100, 20)

    def init_tray(self):
        """初始化系统托盘"""
        from tray_manager import TrayManager
        self.tray_manager = TrayManager(self)

    def mousePressEvent(self, event):
        """鼠标按下事件，用于实现窗口拖动"""
        app_window_manager.mousePressEvent_handler(self, event)

    def mouseMoveEvent(self, event):
        """鼠标移动事件，用于实现窗口拖动"""
        app_window_manager.mouseMoveEvent_handler(self,event)

    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        app_window_manager.mouseReleaseEvent_handler(self,event)

    def on_control_state_changed(self, unlocked):
        """处理控制窗口状态改变事件"""
        app_window_manager.on_control_state_changed(self,unlocked)

    def on_replace_commander(self):
        """处理替换指挥官按钮的点击事件"""
        if hasattr(self, 'commander_selector'):
            # 切换指挥官选择器窗口的打开/关闭状态
            self.commander_selector.toggle_window()

    def closeEvent(self, event):
        """关闭事件"""
        event.ignore()
        self.hide()

    def handle_progress_update(self, data):
        """处理进度更新信号"""
        if data[0] == 'update_map':
            # 在下拉框中查找并选择地图
            map_name = data[1]
            self.logger.info(f'收到地图更新信号: {map_name}')

            # 如果是新游戏开始，强制更新地图
            index = self.combo_box.findText(map_name)
            if index >= 0:
                self.logger.info(f'找到地图 {map_name}，更新下拉框选择')
                # 暂时禁用手动选择标志
                self.manual_map_selection = False
                self.combo_box.setCurrentIndex(index)
                # 手动调用地图选择事件处理函数，确保加载地图文件
                map_loader.handle_map_selection(self, map_name)
            else:
                self.logger.warning(f'未在下拉框中找到地图: {map_name}')

    def on_version_selected(self):
        map_loader.handle_version_selection(self)

    def on_map_selected(self, map_name):
        map_loader.handle_map_selection(self,map_name)


    def on_text_double_click(self, event):
        """处理表格区域双击事件"""
        if event.button() == Qt.LeftButton:
            selected_items = self.table_area.selectedItems()
            if selected_items:
                # 获取选中行的完整内容
                row = selected_items[0].row()
                time_item = self.table_area.item(row, 0)
                event_item = self.table_area.item(row, 1)
                army_item = self.table_area.item(row, 2)
                if time_item and event_item:
                    time_text = time_item.text().strip()
                    event_text = event_item.text().strip()
                    army_text = army_item.text().strip() if army_item else ""
                    selected_text = f"{time_text}\t{event_text}\t{army_text}" if time_text and army_text.strip() else (
                        f"{time_text}\t{event_text}" if time_text else event_text)
                    #self.show_toast(selected_text, config.TOAST_DURATION, force_show=True)  # 设置5000毫秒（5秒）后自动消失
            event.accept()

    def get_text(self, key):
        """获取多语言文本"""
        return language_manager.get_text(self,key)

    def on_language_changed(self, lang):
        return language_manager.on_language_changed(self,lang)

    def handle_artifact_shortcut(self):
        # 如果窗口可见，则销毁图片
        if self.artifact_window.isVisible():
            self.artifact_window.destroy_images()
            self.artifact_window.hide()
        else:
            # 获取当前选择的地图名称并显示对应的神器图片
            try:
                current_map = self.combo_box.currentText()
                if current_map:
                    self.artifact_window.show_artifact(current_map, config.ARTIFACTS_IMG_OPACITY,
                                                       config.ARTIFACTS_IMG_GRAY)
            except Exception as e:
                self.logger.error(f'draw artifacts layer failed: {str(e)}')
                self.logger.error(traceback.format_exc())


    def closeEvent(self, event):
        """窗口关闭事件处理"""
        try:
            if self.malwarfare_handler is not None:
                self.logger.info("应用关闭，正在关闭 MalwarfareMapHandler。")
                self.malwarfare_handler.shutdown()
                self.malwarfare_handler = None
            # 清理全局快捷键
            config_hotkeys.unhook_global_hotkeys(self)
            self.logger.info('已清理所有全局快捷键')
        except Exception as e:
            self.logger.error(f'清理全局快捷键失败: {str(e)}')
            self.logger.error(traceback.format_exc())

        # 调用父类的closeEvent
        super().closeEvent(event)

    def showEvent(self, event):
        """窗口显示事件，确保窗口始终保持在最上层"""
        super().showEvent(event)
        app_window_manager.showEvent_handler(self, event)