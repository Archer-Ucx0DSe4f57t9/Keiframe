import os
from PIL import ImageGrab
from datetime import datetime
import win32gui
import keyboard  # pip install keyboard

# 找到游戏窗口
def get_window_hwnd():
    for name in ["StarCraft II", "《星际争霸II》"]:
        hwnd = win32gui.FindWindow(None, name)
        if hwnd:
            return hwnd

hwnd = get_window_hwnd()

def screenshot_client_area():
    """对客户区截图"""
    if not hwnd:
        print("未找到窗口")
        return

    # 获取客户区矩形（相对坐标）
    client_rect = win32gui.GetClientRect(hwnd)

    # 转换成屏幕绝对坐标
    left_top = win32gui.ClientToScreen(hwnd, (client_rect[0], client_rect[1]))
    right_bottom = win32gui.ClientToScreen(hwnd, (client_rect[2], client_rect[3]))
    bbox = (*left_top, *right_bottom)

    # 截图
    img = ImageGrab.grab(bbox)

    # 文件名加上后缀
    time_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    save_path = f"screenshot_{time_str}.png"

    img.save(save_path)
    print(f"已保存客户区截图: {save_path}")

if __name__ == "__main__":
    print("程序已启动，按 Alt+S 截图（按 Ctrl+C 退出）")

    # 监听全局热键 Alt+S
    keyboard.add_hotkey("alt+s", screenshot_client_area)

    # 保持程序运行
    keyboard.wait()
