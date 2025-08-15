# test_script.py

import asyncio
import aiohttp
import time
import sys
from unittest.mock import Mock
from PyQt5 import QtCore

# 导入整个 mainfunctions 模块
import mainfunctions

# 配置日志
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# ... (MockSignal 类和 get_game_screen 函数保持不变) ...
# 注意：你需要将 get_game_screen 移动到你的 mainfunctions.py 文件中，或者
# 在 test_script.py 中重新定义它。

async def monitor_globals(session: aiohttp.ClientSession):
    """一个独立的协程，用于监控全局变量并打印状态。"""
    last_print_time = time.time()
    while not mainfunctions.state.app_closing:  # 使用 state 实例
        if time.time() - last_print_time >= 1:
            logging.info("--- 全局变量监控 ---")
            logging.info(f"当前游戏ID: {mainfunctions.state.current_game_id}")
            logging.info(f"最近玩家数据: {mainfunctions.state.most_recent_playerdata}")

            # 使用 mainfunctions 模块中的 get_game_screen
            screen_status = await mainfunctions.get_game_screen(session)
            logging.info(f"游戏屏幕状态: {screen_status}")

            last_print_time = time.time()
        await asyncio.sleep(0.1)
    logging.info("监控结束。")


async def main():
    """主测试函数，启动所有异步任务。"""
    mock_progress_signal = Mock(spec=QtCore.pyqtSignal)
    async with aiohttp.ClientSession() as session:
        scheduler_task = asyncio.create_task(mainfunctions.check_for_new_game_scheduler(mock_progress_signal))
        monitor_task = asyncio.create_task(monitor_globals(session))

        logging.info("所有任务已启动。程序将在 60 秒后自动退出。")
        try:
            await asyncio.sleep(60)
        finally:
            logging.info("正在关闭程序...")
            mainfunctions.state.app_closing = True
            scheduler_task.cancel()
            monitor_task.cancel()
            try:
                await asyncio.gather(scheduler_task, monitor_task, return_exceptions=True)
            except Exception:
                pass
            logging.info("程序已退出。")


if __name__ == "__main__":
    try:
        mainfunctions.config.debug_mode = False
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("用户中断了程序。")