import win32gui

hwnd = win32gui.FindWindow(None, "StarCraft II")
def get_user_window_info():

    # 客户区大小（内容区，不含边框+标题栏）
    client_rect = win32gui.GetClientRect(hwnd)

    # 客户区左上角相对坐标 -> 转换为屏幕绝对坐标
    client_left_top = win32gui.ClientToScreen(hwnd, (client_rect[0], client_rect[1]))
    client_right_bottom = win32gui.ClientToScreen(hwnd, (client_rect[2], client_rect[3]))
    client_rect_screen = (*client_left_top, *client_right_bottom)

    return {             # 包含边框
        "客户区矩形": client_rect_screen,  # 实际内容区域
        "客户区大小": (client_rect[2]-client_rect[0], client_rect[3]-client_rect[1])
    }

info = get_user_window_info()
print(info)