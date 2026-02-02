import os
import sys
import json
import traceback
import threading, asyncio
from PyQt5.QtWidgets import (QMainWindow, QApplication,QMessageBox)
from control_window import ControlWindow
from PyQt5.QtCore import Qt, QTimer, QPoint, pyqtSignal
from PyQt5 import QtCore

from src import  config, ui_setup, game_state_service, config_hotkeys, game_time_handler, app_window_manager, language_manager, image_util
from src.map_handlers import map_loader
from src.output.toast_manager import ToastManager
from src.mutaor_handlers.mutator_and_enemy_race_recognizer import Mutator_and_enemy_race_recognizer
from src.memo_overlay import MemoOverlay
from src.settings_window import SettingsWindow
from src.countdown_manager import CountdownManager
from src.utils.fileutil import get_project_root
from src.db.db_manager import DBManager

class TimerWindow(QMainWindow):
    # 创建信号用于地图更新
    progress_signal = QtCore.pyqtSignal(list)
    toggle_artifact_signal = pyqtSignal()
    mutator_and_enemy_race_recognition_signal = QtCore.pyqtSignal(dict)
    

    # 定义信号，用于线程安全地激活各种快捷键
    memo_signal = pyqtSignal(str)
    countdown_hotkey_signal = pyqtSignal()
    map_switch_signal = pyqtSignal()      # 新增：地图切换信号
    lock_signal = pyqtSignal()            # 新增：锁定信号
    screenshot_signal = pyqtSignal()      # 新增：截图信号
    
    def get_screen_resolution(self):
        return app_window_manager.get_screen_resolution()

    def _run_async_game_scheduler(self, progress_signal):
        """在新线程中启动 asyncio 事件循环"""
        asyncio.run(game_state_service.check_for_new_game_scheduler(progress_signal))


    def __init__(self):
        super().__init__()
        
        # 初始化数据库管理器
        self.db_manager = DBManager()
        # 获取数据库连接
        self.maps_db = self.db_manager.get_maps_conn()
        self.mutators_db = self.db_manager.get_mutators_conn()
        #self.enemies_db = self.db_manager.get_enemies_conn()#暂不可用
        
        #在最开始安全地初始化 control_window 为 None
        # 万一在真正创建前触发了 moveEvent，它可以通过 hasattr() 或 try/except 优雅地失败。
        self.control_window = None
        
        #启动时加载用户自定义配置 (这步最好放在程序入口最开始)
        self.apply_user_settings()

        # 初始化突变因子和种族识别器
        self.mutator_and_enemy_race_recognizer = Mutator_and_enemy_race_recognizer(recognition_signal = self.mutator_and_enemy_race_recognition_signal)
        self.mutator_and_enemy_race_recognizer.reset_and_start() # 启动识别线程

        # 设置窗口属性以支持DPI缩放
        self.setAttribute(Qt.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WA_NativeWindow)
        
        # 初始化日志记录器
        from src.utils.logging_util import get_logger
        self.logger = get_logger(__name__)
        self.logger.info('SC2 Timer 启动')

        
        # 初始化状态
        self.current_time = ""
        self.drag_position = QPoint(0, 0)
        self.game_state = game_state_service.state

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

        self.ctrl_pressed = False
        self.is_temp_unlocked = False 
        '''
        # [新增] 实例化监听器并连接信号
        self.global_listener = GlobalKeyListener(parent=self)
        self.global_listener.ctrl_state_changed.connect(self.set_ctrl_state)
        self.global_listener.start_listening()
        '''
        
        #笔记按钮功能
        self.memo_overlay = MemoOverlay()
        if hasattr(self, 'memo_btn'):
            self.memo_btn.clicked.connect(lambda: self.show_memo('temp'))#temp模式防止遮住导致按不了按钮
        #连接信号到槽 (为了解决线程安全问题)
        self.memo_signal.connect(self.show_memo)
        self.countdown_hotkey_signal.connect(self.process_countdown_hotkey_logic)
        self.map_switch_signal.connect(self.process_map_switch_logic)
        self.lock_signal.connect(self.process_lock_logic)
        self.screenshot_signal.connect(self.handle_screenshot_logic) # 连接到实际截图逻辑
        
        #倒计时按钮功能
        self.countdown_manager = CountdownManager(self, self.toast_manager)
        if hasattr(self, 'countdown_btn'):
            self.countdown_btn.clicked.connect(self.trigger_countdown_selection)
        
        #设置按钮功能
        if hasattr(self, 'setting_btn'): 
            self.setting_btn.clicked.connect(self.open_settings)
            
        self.settings_window = None
        
        #退出按钮功能
        if hasattr(self, 'exit_btn'): 
            self.exit_btn.clicked.connect(self.safe_exit)
        
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

        #连接突变因子和种族识
        self.mutator_and_enemy_race_recognition_signal.connect(self.handle_mutator_and_enemy_race_recognition_update)

        #延迟开启主控制界面
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

    
    # === 线程安全的快捷键处理逻辑 ===
    #1. 地图切换
    def handle_map_switch_hotkey(self):
        """供后台线程调用：仅发射信号"""
        self.map_switch_signal.emit()

    def process_map_switch_logic(self):
        """主线程执行：实际UI操作"""
        self.logger.info(f'检测到地图切换快捷键组合: {config.MAP_SHORTCUT}')
        if self.map_version_group.isVisible():
            current_btn = None
            for btn in self.version_buttons:
                if btn.isChecked():
                    current_btn = btn
                    break
            
            if current_btn:
                current_idx = self.version_buttons.index(current_btn)
                next_idx = (current_idx + 1) % len(self.version_buttons)
                self.logger.info(f'从版本 {current_btn.text()} 切换到版本 {self.version_buttons[next_idx].text()}')
                self.version_buttons[next_idx].click()
        else:
            self.logger.info('当前地图不支持A/B版本切换')

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

    # 3. 截图
    def handle_screenshot_hotkey(self):
        """供后台线程调用：仅发射信号"""
        self.screenshot_signal.emit()
    
    def handle_screenshot_logic(self):
        """主线程执行：截图逻辑 (原 handle_screenshot_hotkey 内容移动至此)"""
        # ... (原 handle_screenshot_hotkey 的完整代码内容) ...
        if not config.DEBUG_SHOW_ENEMY_INFO_SQUARE:
            return
        try:
            successful_captures = 0
            for rect in self.rect_screenshots:
                try:
                    save_path = image_util.capture_screen_rect(rect)
                    if save_path:
                        self.logger.info(f'成功保存截图到: {save_path}')
                        successful_captures += 1
                except Exception as capture_error:
                    self.logger.error(f'区域截图失败: {str(capture_error)}')
            # ... (日志记录)
        except Exception as e:
            self.logger.error(f'截图处理失败: {str(e)}')
            self.logger.error(traceback.format_exc())

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

    def setup_search_box_connections(self, files):
        ####################
        # 用户输入搜索
        # 清空搜索框的定时器->现在在ui_setup实现

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

    def closeEvent(self, event):
        """关闭事件"""
        event.ignore()
        self.hide()

    def handle_progress_update(self, data):
        """处理进度更新信号"""
        action = data[0]

        if action == 'update_map':
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

        #新游戏时清除所有原有的计时器
        elif action == 'reset_game_info':
            self.logger.warning('收到新游戏信号，正在重置识别器和游戏状态')
            # 重置识别器状态，并重新开始扫描
            if hasattr(self, 'mutator_and_enemy_race_recognizer') and self.mutator_and_enemy_race_recognizer:
                 self.mutator_and_enemy_race_recognizer.reset_and_start() # 调用识别器的重置和启动方法

            # 清除全局状态中的种族和突变因子
            game_state_service.state.enemy_race = None
            game_state_service.state.active_mutators = None
            
            # 清空自定义倒计时
            if hasattr(self, 'countdown_manager') and self.countdown_manager:
                self.countdown_manager.clear_all_countdowns()
            
            # 清除所有残留的 Toast（包括地图事件）
            if hasattr(self, 'toast_manager') and self.toast_manager:
                self.toast_manager.clear_all_alerts()


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
        """处理种族和突变因子识别结果的更新"""
        race = results.get("race")
        mutators = results.get("mutators")

        if race:
            self.logger.info(f"UI接收到确认种族: {race}")
            game_state_service.state.enemy_race = race

            current_map = self.combo_box.currentText()
            if current_map:
                map_loader.handle_map_selection(self, current_map)
            # 如果种族更新，强制同步突变因子按钮状态    
            if hasattr(self, 'mutator_manager') and self.mutator_manager and game_state_service.state.active_mutators is not None:
                self.logger.info(f"种族已更新{race}，强制重新同步突变因子变式。")
                self.mutator_manager.sync_mutator_toggles(game_state_service.state.active_mutators)

        if mutators is not None:
            # 只有当 mutators 不为 None（即识别完成，可能是空列表）时才更新
            self.logger.info(f"UI接收到确认突变因子: {mutators}")
            game_state_service.state.active_mutators = mutators
            # 调用 MutatorManager 来同步按钮状态
            if hasattr(self, 'mutator_manager') and self.mutator_manager:
                self.mutator_manager.sync_mutator_toggles(mutators)

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
        
        json_path = os.path.join(get_project_root(), 'settings.json')
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    user_settings = json.load(f)
                    
                # 动态更新 config 模块的属性
                for key, value in user_settings.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
                        # print(f"已更新配置: {key} = {value}")
            except Exception as e:
                print(f"加载用户配置失败: {e}")

    def open_settings(self):
        """打开设置窗口"""
        if self.settings_window is None:
            # 传递 self 作为父级，确保窗口在应用程序内正确管理
            self.settings_window = SettingsWindow(self) 
            self.settings_window.settings_saved.connect(self.handle_settings_update)
        
        # 1. 打开模态窗口前，卸载全局快捷键
        # 这能防止打字时的按键冲突导致的闪退，也能防止误触游戏快捷键
        config_hotkeys.unhook_global_hotkeys(self)
        
        # 2. 运行设置窗口 (阻塞直到关闭)
        self.settings_window.exec_() 
        
        # 3. 【关键修复】关闭窗口后，重新注册全局快捷键
        config_hotkeys.init_global_hotkeys(self)
        
        # 4. 重新应用可能修改了的配置
        self.apply_user_settings()

    def handle_settings_update(self, new_settings):
        """
        当设置窗口保存后，处理实时更新逻辑
        有些设置可以直接生效（如颜色、透明度），有些可能需要重启
        """
        # 1. 更新 config 内存中的值
        for key, value in new_settings.items():
            setattr(config, key, value)
        self.logger.info("配置已更新，部分功能已重载")

    def showEvent(self, event):
        """窗口显示事件，确保窗口始终保持在最上层"""
        super().showEvent(event)
        app_window_manager.showEvent_handler(self, event)
        
    def safe_exit(self):
        """关闭所有后台处理器和监听器"""
        try:
            #1.关闭净网识别
            if hasattr(self, 'malwarfare_handler') and self.malwarfare_handler is not None:
                self.logger.info("应用关闭，正在关闭 MalwarfareMapHandler。")
                self.malwarfare_handler.shutdown()
                self.malwarfare_handler = None

            #2.关闭突变因子识别
            if hasattr(self, 'mutator_and_enemy_race_recognizer') and self.mutator_and_enemy_race_recognizer:
                self.mutator_and_enemy_race_recognizer.shutdown()
                self.logger.info("突变因子和种族识别器已关闭。")

            #3.设置全局标志位，通知所有 asyncio 循环停止
            game_state_service.state.app_closing = True

            # 4.清理全局快捷
            config_hotkeys.unhook_global_hotkeys(self)
            
            #self.logger.info("清理完成，程序退出。")
            QApplication.instance().quit()
            
        except Exception as e:
            self.logger.error(f'清理失败，无法正常退出: {str(e)}')
            self.logger.error(traceback.format_exc())


    def closeEvent(self, event):
        """窗口关闭事件处理"""
        try:
            if self.malwarfare_handler is not None:
                self.logger.info("应用关闭，正在关闭 MalwarfareMapHandler。")
                self.malwarfare_handler.shutdown()
                self.malwarfare_handler = None

            if hasattr(self, 'mutator_and_enemy_race_recognizer') and self.mutator_and_enemy_race_recognizer:
                self.mutator_and_enemy_race_recognizer.shutdown()
                self.logger.info("突变因子和种族识别器已关闭。")
                
            if hasattr(self, 'global_listener') and self.global_listener:
                self.global_listener.stop_listening()
                self.logger.info("按键监听已关闭。")

            # 清理全局快捷键
            config_hotkeys.unhook_global_hotkeys(self)
            self.logger.info('已清理')
        except Exception as e:
            self.logger.error(f'清理失败: {str(e)}')
            self.logger.error(traceback.format_exc())

        # 调用父类的closeEvent
        super().closeEvent(event)
