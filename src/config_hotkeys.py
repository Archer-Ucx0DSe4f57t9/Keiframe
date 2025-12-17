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
        memo_temp_key = getattr(config, 'MEMO_TEMP_SHORTCUT', '`').replace(' ', '').lower()
        memo_toggle_key = getattr(config, 'MEMO_TOGGLE_SHORTCUT', 'backslash').replace(' ', '').lower()
        
        # 注册全局快捷键，使用 lambda 避免直接绑定实例方法
        keyboard.add_hotkey(map_shortcut, lambda: handle_map_switch_hotkey(window))
        keyboard.add_hotkey(lock_shortcut, lambda: handle_lock_shortcut(window))
        # 截图逻辑保留在主类，这里直接调用
        keyboard.add_hotkey(screenshot_shortcut, lambda: window.handle_screenshot_hotkey()) 
        
        #注册显示笔记的快捷键
        keyboard.add_hotkey(memo_temp_key, lambda: handle_memo_hotkey(window, 'temp'))
        keyboard.add_hotkey(memo_toggle_key, lambda: handle_memo_hotkey(window, 'toggle'))
        
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

def handle_memo_hotkey(window, mode):
    """处理 Memo 快捷键"""
    # 确保在主线程执行 GUI 操作，通过信号或者 invokeMethod
    # 这里假设 window 有一个 trigger_memo_signal 信号连接到了 memo_overlay 的方法
    # 或者直接调用 window 的方法，让 window 去调用 overlay
    
    # 推荐做法：在 TimerWindow 中定义一个方法来中转
    try:
        if hasattr(window, 'trigger_memo_display'):
             # 由于 keyboard 库在独立线程，直接调用 GUI 可能会崩，建议用信号
             # 但如果 trigger_memo_display 里只是发射信号，则是安全的
             window.trigger_memo_display(mode)
    except Exception as e:
        print(f"Memo hotkey error: {e}")

def unhook_global_hotkeys(window):
    """窗口关闭时清理全局快捷键"""
    try:
        keyboard.unhook_all()
        window.logger.info('已清理所有全局快捷键')
    except Exception as e:
        window.logger.error(f'清理全局快捷键失败: {str(e)}')
        window.logger.error(traceback.format_exc())