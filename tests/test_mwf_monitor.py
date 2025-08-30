import sys
import os
import time
import logging
from logging.handlers import RotatingFileHandler

# --- 设置项目路径，确保能导入其他模块 ---
# 这个脚本假设它位于 tests/ 文件夹下，而您的源码位于 src/ 文件夹下
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.map_handlers.malwarfare_map_handler import MalwarfareMapHandler
from src.window_utils import get_sc2_window_geometry
import src.config as config

# --- Mock/辅助类 ---
class ConsoleToastManager:
    """一个在控制台打印Toast消息的模拟管理器。"""
    def show_simple_toast(self, msg):
        print(f"[TOAST] {msg}")
    def hide_toast(self):
        print("[TOAST] Hiding toast...")

def setup_logger():
    """配置日志记录器，同时输出到控制台和文件。"""
    logger = logging.getLogger("MalwarfareLiveTest")
    logger.setLevel(logging.DEBUG) # 设置最低日志级别

    # 防止重复添加handler
    if logger.hasHandlers():
        logger.handlers.clear()

    # 控制台处理器
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO) # 控制台只显示INFO及以上级别的信息
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # 文件处理器 (记录DEBUG及以上所有信息)
    log_file_path = "live_test_log.log"
    fh = RotatingFileHandler(log_file_path, maxBytes=1024*1024*5, backupCount=3, encoding='utf-8')
    fh.setLevel(logging.DEBUG) # 文件记录所有DEBUG信息
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(file_formatter)
    logger.addHandler(fh)

    return logger

def main():
    """主函数，负责初始化和运行实时识别循环。"""
    logger = setup_logger()
    toast_manager = ConsoleToastManager()

    logger.info("="*50)
    logger.info(" 恶意软件战争 - 实时OCR测试程序 ")
    logger.info("="*50)

    try:
        # --- 初始化Handler ---
        # 注意：这里传入的是真实的 get_sc2_window_geometry 函数
        handler = MalwarfareMapHandler(
            config=config,
            toast_manager=toast_manager,
            get_window_geometry_func=lambda: get_sc2_window_geometry('StarCraft II'),
            logger=logger,
            debug=True # 开启Debug模式，会保存中间图像
        )
        
        # 启动后台识别线程
        handler.start()

        # --- 主循环，用于周期性获取和打印结果 ---
        logger.info("识别程序已启动。按 Ctrl+C 停止。")
        while True:
            # 从handler中获取线程安全的结果
            with handler._result_lock:
                current_result = handler._latest_result
            
            # 在控制台实时显示最新结果
            # 使用\r实现原地更新，避免刷屏
            if current_result:
                print(f"\r[实时结果] Count: {current_result.get('n', 'N/A')}, Time: {current_result.get('time', 'N/A')}", end="")
            else:
                print("\r[实时结果] 正在等待第一次识别...", end="")

            time.sleep(1) # 每秒更新一次显示

    except KeyboardInterrupt:
        logger.info("\n收到停止信号，正在清理...")
    except Exception as e:
        logger.error(f"发生未处理的异常: {e}", exc_info=True)
    finally:
        if 'handler' in locals() and handler:
            handler.cleanup()
        logger.info("程序已退出。")


if __name__ == '__main__':
    main()