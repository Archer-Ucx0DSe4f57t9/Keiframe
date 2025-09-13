import sys
import os
import time
import logging
from logging.handlers import RotatingFileHandler

# --- 设置项目路径，确保能导入其他模块 ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.map_handlers.malwarfare_map_handler import MalwarfareMapHandler

# --- Mock/辅助类 ---
class ConsoleToastManager:
    """一个在控制台打印Toast消息的模拟管理器。"""
    def show_simple_toast(self, msg):
        # 在实时测试中，handler内部的logger已经提供了足够的信息，
        # 我们可以简化这里的输出，避免刷屏。
        # print(f"[TOAST] {msg}") 
        pass
    def hide_toast(self):
        pass

def setup_logger():
    """配置日志记录器，同时输出到控制台和文件。"""
    logger = logging.getLogger("MalwarfareLiveTest")
    logger.setLevel(logging.DEBUG)

    if logger.hasHandlers():
        logger.handlers.clear()

    # 控制台处理器
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # 文件处理器 (记录DEBUG及以上所有信息)
    log_file_path = "live_test_log.log"
    fh = RotatingFileHandler(log_file_path, maxBytes=1024*1024*5, backupCount=3, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(file_formatter)
    logger.addHandler(fh)

    return logger

def main():
    """主函数，负责初始化和运行实时识别循环。"""
    logger = setup_logger()
    toast_manager = ConsoleToastManager()

    logger.info("="*50)

    handler = None
    try:
        # --- 初始化Handler ---
        # 最新版的Handler内部逻辑已非常复杂，但初始化接口保持不变
        handler = MalwarfareMapHandler(
            toast_manager=toast_manager,
            debug=False # 设为True可在 'debugpath' 看到中间图像，用于诊断
        )

        # 启动后台识别线程
        # handler内部会自动处理UI状态探测、颜色校准等所有复杂逻辑
        handler.start()

        
        # --- 主循环，用于周期性获取和打印结果 ---
        logger.info("识别程序已启动。按 Ctrl+C 停止。")
        last_printed_result = None
        while True:
            # 从handler中获取线程安全的结果
            current_result = None
            with handler._result_lock:
                current_result = handler._latest_result

            # 只有当结果变化时才更新显示，减少控制台闪烁
            if current_result != last_printed_result:
                if current_result:
                    print(f"\r[实时结果] Count: {current_result.get('n', 'N/A')}, Time: {current_result.get('time', 'N/A')}  is_paused:{current_result.get('is_paused','N/A')} ", end="")
                else:
                    print("\r[实时结果] 等待游戏窗口及首次识别...", end="")
                last_printed_result = current_result

            time.sleep(0.5) # 每0.5秒检查一次结果

    except KeyboardInterrupt:
        logger.info("\n收到停止信号，正在清理...")
    except Exception as e:
        logger.error(f"发生未处理的异常: {e}", exc_info=True)
    finally:
        if handler:
            handler.cleanup()
        logger.info("程序已退出。")


if __name__ == '__main__':
    main()