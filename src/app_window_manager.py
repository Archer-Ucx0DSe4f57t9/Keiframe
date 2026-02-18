import sys
import traceback
import ctypes
from ctypes import wintypes
import win32con # 需要在环境中安装 pypiwin32 库
from PyQt5.QtCore import Qt, QRect, QPoint
from PyQt5.QtWidgets import QApplication
from src import config



# 辅助函数 1: 获取屏幕分辨率
def get_screen_resolution():
    """获取屏幕分辨率 (原 TimerWindow.get_screen_resolution)"""
    user32 = ctypes.windll.user32
    # user32.SetProcessDPIAware() # 原代码中注释了，保持不变
    width = user32.GetSystemMetrics(0)
    height = user32.GetSystemMetrics(1)
    return width, height

# 辅助函数 2: 更新控制窗口位置
def update_control_window_position(window):
    """保持控制窗口与主窗口位置同步 (原 TimerWindow.update_control_window_position)"""
    
    if window.control_window is None:
        return
    
    current_screen = window.get_current_screen()
    screen_geometry = current_screen.geometry()

    # 确保控制窗口不会超出屏幕顶部
    new_y = max(screen_geometry.y(), window.y() - window.control_window.height())
    window.control_window.move(window.x(), new_y)

# 辅助函数 3: 鼠标按下事件处理
def mousePressEvent_handler(window, event):
    """鼠标按下事件，用于实现窗口拖动 (原 TimerWindow.mousePressEvent)"""
    # 检查窗口是否处于可点击状态（非锁定状态）
    is_clickable = not window.testAttribute(Qt.WA_TransparentForMouseEvents)
    pos = event.pos()
    icon_size = 25
    drag_x = config.MAIN_WINDOW_WIDTH - icon_size - 5 
    DRAG_AREA = QRect(drag_x, 0, 35, 35)
    SEARCH_BOX_AREA = QRect(10, 5, 50, 30)
    
    if event.button() != Qt.LeftButton:
        event.ignore()
        return
    
    if is_clickable:  # 窗口可点击时
        if DRAG_AREA.contains(pos):
            window.drag_position = event.globalPos() - window.frameGeometry().topLeft()
            window.is_dragging = True
            event.accept()

    else:
        if window.ctrl_pressed and False:#临时弃置，不使用

            if DRAG_AREA.contains(pos):
                
                # 临时禁用事件穿透，确保后续的 mouseMoveEvent 能被接收！
                window.setAttribute(Qt.WA_TransparentForMouseEvents, False)
                window.is_temp_unlocked = True # 使用临时解锁标志
                
                window.drag_position = event.globalPos() - window.frameGeometry().topLeft()
                window.is_dragging = True
                event.accept()

            elif SEARCH_BOX_AREA.contains(pos):
                # 临时禁用事件穿透
                window.setAttribute(Qt.WA_TransparentForMouseEvents, False)
                
                # 允许当前事件被接受，让搜索框接收到点击和焦点
                event.accept()
                
                # 延迟恢复事件穿透属性
                # QTimer.singleShot(100, lambda: window.setAttribute(Qt.WA_TransparentForMouseEvents, True))
                # ⚠️ 注意：直接恢复会导致用户输入一个字符后就无法继续输入。
                #     我们必须在 mouseReleaseEvent 或用户失去焦点时恢复。
                
                # 临时启用鼠标事件，并让 TimerWindow 知道这次是临时启用
                window.is_temp_unlocked = True 
                
                # 确保搜索框获得焦点
                window.search_box.setFocus()
                
                # 退出函数
                return
            else:
                event.ignore()
        else:
            event.ignore()

# 辅助函数 4: 鼠标移动事件处理
def mouseMoveEvent_handler(window, event):
    """鼠标移动事件，用于实现窗口拖动 (原 TimerWindow.mouseMoveEvent)"""
    if event.buttons() == Qt.LeftButton and hasattr(window, 'is_dragging') and window.is_dragging:
        window.move(event.globalPos() - window.drag_position)
        event.accept()

# 辅助函数 5: 鼠标释放事件处理
def mouseReleaseEvent_handler(window, event):
    """鼠标释放事件 (原 TimerWindow.mouseReleaseEvent)"""
    if event.button() == Qt.LeftButton:
        window.is_dragging = False
        event.accept()

    if hasattr(window, 'is_temp_unlocked') and window.is_temp_unlocked:
        
        # 检查 ControlWindow 状态（假设 control_window 有 is_unlocked 属性）
        is_control_unlocked = getattr(window.control_window, 'is_unlocked', False) 
        
        # 如果 ControlWindow 处于锁定状态，我们才恢复事件穿透属性
        if not is_control_unlocked:
            window.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            window.is_temp_unlocked = False # 重置临时标志
        
    else:
        event.ignore()

# 辅助函数 6: 控制状态改变（点击穿透）
def on_control_state_changed(window, unlocked):
    """处理控制窗口状态改变事件（点击穿透）(原 TimerWindow.on_control_state_changed)"""
    window.logger.info(f'控制窗口状态改变: unlocked={unlocked}')

    # 在Windows平台上，直接使用Windows API设置窗口样式
    if sys.platform == 'win32':
        try:
            # 定义Windows API常量
            #告诉 Windows API 函数（如 GetWindowLong 或 SetWindowLong）想要读取或修改的是窗口的扩展样式集。
            GWL_EXSTYLE = win32con.GWL_EXSTYLE
            #启用窗口的点击穿透。它使窗口对鼠标和用户输入透明.
            WS_EX_TRANSPARENT = win32con.WS_EX_TRANSPARENT
            #启用分层窗口。允许设置窗口的透明度（不透明度）或使用复杂形状.
            WS_EX_LAYERED = win32con.WS_EX_LAYERED

            # 获取窗口句柄
            hwnd = int(window.winId())

            # 获取当前窗口样式
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

            if not unlocked:  # 锁定状态（不可点击）
                # 添加透明样式
                new_ex_style = ex_style | WS_EX_TRANSPARENT | WS_EX_LAYERED
            else:  # 解锁状态（可点击）
                # 移除透明样式，但保留WS_EX_LAYERED
                new_ex_style = (ex_style & ~WS_EX_TRANSPARENT) | WS_EX_LAYERED

            # 设置新样式
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex_style)

            # 强制窗口重绘
            ctypes.windll.user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                win32con.SWP_NOSIZE | win32con.SWP_NOMOVE | win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED
            )

        except Exception as e:
            window.logger.error(f'设置Windows平台点击穿透失败: {str(e)}')
            window.logger.error(traceback.format_exc())
    else:
        # 非Windows平台使用Qt的方法
        window.hide()  

        if not unlocked:  # 锁定状态（不可点击）
            window.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        else:  # 解锁状态（可点击）
            window.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        window.show()

    # 更新突变按钮的状态
    if hasattr(window, 'mutator_manager'):
        window.mutator_manager.on_control_state_changed(unlocked)

# 辅助函数 7: 关闭事件处理 （闲置中）
def closeEvent_handler(window, event):
    """关闭事件处理 (原 TimerWindow.closeEvent)"""
    event.ignore()
    window.hide()

# 辅助函数 8: 窗口显示事件处理
def showEvent_handler(window, event):
    """窗口显示事件，确保窗口始终保持在最上层 (原 TimerWindow.showEvent)"""
    # 置顶处理（部分代码已在 __init__ 中，这里是确保在 show 之后再次置顶）
    if sys.platform == 'win32':
        import win32gui
        import win32con
        hwnd = int(window.winId())
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)