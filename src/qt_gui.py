from PyQt5.QtWidgets import QMainWindow, QApplication
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5 import QtCore

from src import config, ui_setup, game_state_service, app_window_manager, language_manager
from src.app_runtime import AppRuntime
from src.map_handlers import map_loader
from src.recognition_controller import (
    create_production_enemy_composition_ocr_provider,
)


class TimerWindow(QMainWindow):
    # 创建信号用于地图更新
    progress_signal = QtCore.pyqtSignal(list)
    toggle_artifact_signal = pyqtSignal()
    mutator_and_enemy_race_recognition_signal = QtCore.pyqtSignal(dict)
    enemy_composition_confirmed_signal = QtCore.pyqtSignal(str)
    

    # 定义信号，用于线程安全地激活各种快捷键
    memo_signal = pyqtSignal(str)
    countdown_hotkey_signal = pyqtSignal()
    map_switch_signal = pyqtSignal()      # 新增：地图切换信号
    lock_signal = pyqtSignal()            # 新增：锁定信号
    
    def get_screen_resolution(self):
        return app_window_manager.get_screen_resolution()

    def _run_async_game_scheduler(self, progress_signal):
        """在新线程中启动 asyncio 事件循环"""
        return self.app_runtime.run_async_game_scheduler(progress_signal)

    def _initialize_enemy_composition_recognition(self):
        self.recognition_controller.initialize_enemy_composition_recognition()


    def __init__(self):
        super().__init__()
        self.app_runtime = AppRuntime(self)
        self.app_runtime.initialize()

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

    
    # === 线程安全的快捷键处理逻辑 ===
    #1. 地图切换
    def handle_map_switch_hotkey(self):
        """供后台线程调用：仅发射信号"""
        self.map_switch_signal.emit()

    def process_map_switch_logic(self):
        """主线程执行：实际UI操作"""
        self.map_selection_controller.process_map_switch_logic()

    # 2. 锁定窗口
    def handle_lock_shortcut(self):
        """供后台线程调用：仅发射信号"""
        self.lock_signal.emit()

    def process_lock_logic(self):
        """主线程执行：实际UI操作"""
        self.logger.info(f'检测到锁定快捷键组合: {config.LOCK_SHORTCUT}')
        if self.control_window:
            self.control_window.is_locked = not self.control_window.is_locked
            self.control_window.update_icon()
            self.control_window.state_changed.emit(not self.control_window.is_locked)

    # 4. 倒计时 (已修复，保持现状，确保名字对应)
    def handle_countdown_hotkey(self):
        self.countdown_hotkey_signal.emit()

    def process_countdown_hotkey_logic(self):
        game_time = 0
        if self.game_state.game_time:
             game_time = float(self.game_state.game_time)
        self.countdown_manager.handle_hotkey_trigger(game_time)

    
    def init_ui(self):
        ui_setup.init_ui(self)

    def setup_search_box_connections(self, map_list):
        self.map_selection_controller.setup_search_box_connections(map_list)

    def init_tray(self):
        """初始化系统托盘"""
        from src.tray_manager import TrayManager
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

    @QtCore.pyqtSlot(str)
    def handle_enemy_composition_confirmed(self, canonical_composition):
        self.recognition_controller.handle_enemy_composition_confirmed(
            canonical_composition
        )

    def handle_progress_update(self, data):
        """处理进度更新信号"""
        action = data[0]

        if action == 'update_map':
            self.map_selection_controller.handle_map_update(data[1])

        #新游戏时清除所有原有的计时器
        elif action == 'reset_game_info':
            self.app_runtime.reset_game_info()


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
            event.accept()

    def trigger_memo_display(self, mode):
        """提供给 config_hotkeys.py 调用的线程安全接口"""
        self.memo_signal.emit(mode)

    def show_memo(self, mode):
        """
        核心调用逻辑
        :param mode: 'temp' or 'toggle'
        """
        try:
            # 假设 game_state_service 已在 TimerWindow 的模块中导入
            current_map = game_state_service.state.current_selected_map
            self.logger.info(f"通过 game_state_service 获取地图: {current_map}")
        except Exception:
            current_map = "Unknown_Map"
            self.logger.warning("无法从 game_state_service 获取当前地图名称，使用默认值。")
                
        self.logger.info(f"触发 Memo 显示: 地图={current_map}, 模式={mode}")
        
        # 调用 Overlay 显示 (注意：如果地图名包含特殊字符，你可能需要清理它以匹配文件名)
        if '-' in current_map:
            cleaned_map_name = current_map.split('-')[0]
        else:
            cleaned_map_name = current_map
        self.memo_overlay.load_and_show(cleaned_map_name, mode)
    
    def get_text(self, key):
        """获取多语言文本"""
        return language_manager.get_text(self,key)

    def on_language_changed(self, lang):
        return language_manager.on_language_changed(self,lang)
    
    #倒计时功能相关
    def trigger_countdown_selection(self):
        game_time = 0
        if self.game_state.game_time:
             game_time = float(self.game_state.game_time)
        self.countdown_manager.start_interaction(game_time)

    def handle_countdown_hotkey(self):
        self.countdown_hotkey_signal.emit()

    def process_countdown_hotkey_logic(self):
        game_time = 0
        if self.game_state.game_time:
             game_time = float(self.game_state.game_time)
        self.countdown_manager.handle_hotkey_trigger(game_time)

    
    # 处理识别器传回突变因子和种族的数据
    def handle_mutator_and_enemy_race_recognition_update(self, results):
        self.recognition_controller.handle_mutator_and_enemy_race_recognition_update(
            results
        )

    #当搜索框失去焦点时，检查是否需要恢复锁定（事件穿透
    def restore_lock_on_search_focus_out(self):
        # 检查窗口当前是否被锁定 (即 is_clickable == False)
        is_currently_locked = self.testAttribute(Qt.WA_TransparentForMouseEvents)

        # 检查是否是临时解锁状态并且窗口当前是解锁的
        if hasattr(self, 'is_temp_unlocked') and self.is_temp_unlocked and not is_currently_locked:
            
            # 检查控制窗口是否被明确设置为解锁状态
            is_control_unlocked = getattr(self.control_window, 'is_unlocked', True) 
            
            # 只有当控制窗口不是明确解锁时，才恢复锁定
            if not is_control_unlocked:
                self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                self.logger.info("搜索框失去焦点，已恢复窗口锁定（事件穿透）。")
                self.is_temp_unlocked = False # 重置临时标志
            # else: 如果控制窗口已经是解锁状态，则不设置穿透属性，保持解锁
            
            
    def apply_user_settings(self):
        """读取json并覆盖config.py中的变量"""
        self.settings_controller.apply_user_settings()

    def open_settings(self):
        """打开设置窗口"""
        self.settings_controller.open_settings()

    def handle_settings_update(self, new_settings):
        self.settings_controller.handle_settings_update(new_settings)

    def showEvent(self, event):
        """窗口显示事件，确保窗口始终保持在最上层"""
        super().showEvent(event)
        app_window_manager.showEvent_handler(self, event)
        
    def safe_exit(self):
        """关闭所有后台处理器和监听器"""
        return self.app_runtime.safe_exit()

    def closeEvent(self, event):
        """窗口关闭事件处理"""
        self.app_runtime.cleanup_on_close()
        super().closeEvent(event)
