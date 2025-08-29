import sys,os
import time
import logging

# 导入你的核心类
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from map_handlers.malwarfare_map_handler import MalwarfareMapHandler


class MockLogger:
    def info(self, message):
        print(f"[INFO] {message}")
    def debug(self, message):
        print(f"[DEBUG] {message}")
    def warning(self, message):
        print(f"[WARNING] {message}")
    def error(self, message):
        print(f"[ERROR] {message}")

class MockToastManager:
    def show_simple_toast(self, message):
        print(f"[TOAST] Displaying: {message}")
    def hide_toast(self):
        print("[TOAST] Hiding toast...")

def main():
    logger = MockLogger()
    handler = MalwarfareMapHandler(
        table_area=None,
        toast_manager=MockToastManager(),
        logger=logger
    )

    print("开始实时 OCR 测试...")
    print("请确保星际争霸2窗口处于激活状态。")
    print("按 Ctrl+C 退出。")

    handler.start()

    try:
        while True:
            # get_latest_parsed_result 内部会通过线程自动更新
            result = handler.get_latest_parsed_result()
            
            # 清除控制台，实时显示最新结果
            # Windows: os.system('cls')
            # macOS/Linux: os.system('clear')
            os.system('cls' if os.name == 'nt' else 'clear')
            
            print("实时 OCR 结果:")
            print("-" * 20)
            if result:
                print(f"状态: {result}")
            else:
                print("状态: 无法解析")
            print("-" * 20)
            
            time.sleep(1) # 每秒更新一次显示

    except KeyboardInterrupt:
        print("\n测试结束，正在清理...")
    finally:
        handler.cleanup()
        print("清理完成。")

if __name__ == "__main__":
    main()