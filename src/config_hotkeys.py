import keyboard
import traceback
import config
from PyQt5.QtCore import Qt

def init_global_hotkeys(window):
    """初始化全局快捷键，并绑定到 TimerWindow 实例的方法 (原 init_global_hotkeys)"""
    try:
        # 解析快捷键配置
        map_shortcut = config.MAP_SHORTCUT.replace(' ', '').lower()
        lock_shortcut = config.LOCK_SHORTCUT.replace(' ', '').lower()
        screenshot_shortcut = config.SCREENSHOT_SHORTCUT.replace(' ', '').lower()
        artifact_shortcut = config.SHOW_ARTIFACT_SHORTCUT.replace(' ', '').lower()

        # 注册全局快捷键，使用 lambda 避免直接绑定实例方法
        keyboard.add_hotkey(map_shortcut, lambda: handle_map_switch_hotkey(window))
        keyboard.add_hotkey(lock_shortcut, lambda: handle_lock_shortcut(window))
        # 截图逻辑保留在主类，这里直接调用
        keyboard.add_hotkey(screenshot_shortcut, lambda: window.handle_screenshot_hotkey()) 
        
        # 使用信号触发神器窗口的切换
        window.toggle_artifact_signal.connect(window.handle_artifact_shortcut)
        keyboard.add_hotkey(artifact_shortcut, window.toggle_artifact_signal.emit)
        
        window.logger.info(
            f'成功注册全局快捷键: {config.MAP_SHORTCUT}, {config.LOCK_SHORTCUT}, {config.SCREENSHOT_SHORTCUT}')

    except Exception as e:
        window.logger.error(f'注册全局快捷键失败: {str(e)}')
        window.logger.error(traceback.format_exc())
        
def handle_lock_shortcut(window):
    """处理锁定快捷键 (原 handle_lock_shortcut)"""
    window.logger.info(f'检测到锁定快捷键组合: {config.LOCK_SHORTCUT}')
    # 切换控制窗口的锁定状态
    window.control_window.is_locked = not window.control_window.is_locked
    window.control_window.update_icon()
    # 发送状态改变信号
    window.control_window.state_changed.emit(not window.control_window.is_locked)

def handle_map_switch_hotkey(window):
    """处理地图切换快捷键 (原 handle_map_switch_hotkey)"""
    window.logger.info(f'检测到地图切换快捷键组合: {config.MAP_SHORTCUT}')
    # 检查当前地图是否为A/B版本
    if window.map_version_group.isVisible():
        window.logger.info('当前地图支持A/B版本切换')
        
        current_btn = None
        for btn in window.version_buttons:
            if btn.isChecked():
                current_btn = btn
                break
        
        if current_btn:
            current_idx = window.version_buttons.index(current_btn)
            next_idx = (current_idx + 1) % len(window.version_buttons)
            window.logger.info(f'从版本 {current_btn.text()} 切换到版本 {window.version_buttons[next_idx].text()}')
            window.version_buttons[next_idx].click()
    else:
        window.logger.info('当前地图不支持A/B版本切换')

def unhook_global_hotkeys(window):
    """窗口关闭时清理全局快捷键"""
    try:
        keyboard.unhook_all()
        window.logger.info('已清理所有全局快捷键')
    except Exception as e:
        window.logger.error(f'清理全局快捷键失败: {str(e)}')
        window.logger.error(traceback.format_exc())