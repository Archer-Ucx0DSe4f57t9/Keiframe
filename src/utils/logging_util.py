import os
import logging
import sys
from datetime import datetime, timedelta
from src import config


_LOG_FILE_PATH_UNSET = object()


def _report_log_error(message, error):
    """日志尚未初始化时，尽量把错误保留在标准错误输出。"""
    try:
        print(f'{message}: {error}', file=sys.stderr)
    except Exception:
        pass


def _try_prepare_log_file(log_file):
    """创建日志目录并探测日志文件是否可追加写入。"""
    try:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        with open(log_file, 'a', encoding='utf-8'):
            pass
        return True
    except OSError as error:
        _report_log_error(f'日志文件不可写，跳过 {log_file}', error)
        return False


def resolve_log_file_path(default_log_file=None, fallback_log_file=None):
    """选择启动时实际使用的日志文件，两个位置都不可写时返回 None。"""
    if default_log_file is None or fallback_log_file is None:
        # fileutil 依赖本模块获取 logger，因此保持延迟导入以避免循环导入。
        from src.utils.fileutil import (
            get_fallback_log_file_path,
            get_log_file_path,
        )

        if default_log_file is None:
            default_log_file = get_log_file_path()
        if fallback_log_file is None:
            fallback_log_file = get_fallback_log_file_path()

    candidates = [default_log_file]
    if fallback_log_file and fallback_log_file != default_log_file:
        candidates.append(fallback_log_file)

    for log_file in candidates:
        if log_file and _try_prepare_log_file(log_file):
            return log_file
    return None


def rotate_log_file(log_path, max_size_mb=1, days_to_keep=7):
    """日志超过限制时保留最近若干天；任何文件错误都不阻止启动。"""
    if not log_path:
        return False

    try:
        if not os.path.exists(log_path):
            return True

        if os.path.getsize(log_path) <= max_size_mb * 1024 * 1024:
            return True

        print(f'Log file exceeds {max_size_mb}MB, cleaning up old entries...')
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        remaining_lines = []

        with open(log_path, 'r', encoding='utf-8') as log_file:
            for line in log_file:
                try:
                    date_str = line.split(' ')[0]
                    log_date = datetime.strptime(date_str, '%Y-%m-%d')
                    if log_date >= cutoff_date:
                        remaining_lines.append(line)
                except (ValueError, IndexError):
                    remaining_lines.append(line)

        # 读取句柄已关闭后才写回，且启动时文件处理器尚未创建。
        with open(log_path, 'w', encoding='utf-8') as log_file:
            log_file.writelines(remaining_lines)
        return True
    except (OSError, UnicodeError) as error:
        _report_log_error(f'日志轮换失败，继续启动 {log_path}', error)
        return False


def setup_logger(base_dir=None, log_file_path=_LOG_FILE_PATH_UNSET):
    """初始化日志配置
    
    Args:
        base_dir: 日志文件存储的基础目录；保留旧的 log/sc2_Keiframe.log 行为
        log_file_path: 已确定的日志文件路径；None 表示仅使用其他日志输出
    """
    if log_file_path is not _LOG_FILE_PATH_UNSET:
        final_log_file = log_file_path
    elif base_dir:
        log_dir = os.path.join(base_dir, 'log')
        log_file = os.path.join(log_dir, 'sc2_Keiframe.log')
        final_log_file = log_file if _try_prepare_log_file(log_file) else None
    else:
        final_log_file = resolve_log_file_path()

    handlers = []
    if final_log_file:
        try:
            handlers.append(
                logging.FileHandler(final_log_file, encoding='utf-8', mode='a')
            )
        except OSError as error:
            _report_log_error(
                f'日志文件处理器创建失败，改用标准错误输出 {final_log_file}',
                error,
            )
            final_log_file = None
    handlers.append(logging.StreamHandler())

    # 配置根日志记录器
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        handlers=handlers,
    )
    return final_log_file


def initialize_logging():
    """选择最终日志路径，在打开文件处理器前轮换并初始化日志。"""
    log_file_path = resolve_log_file_path()
    rotate_log_file(log_file_path)
    return setup_logger(log_file_path=log_file_path)

def get_logger(name):
    """获取指定名称的日志记录器
    
    Args:
        name: 日志记录器名称，通常使用__name__
    
    Returns:
        Logger: 配置好的日志记录器实例
    """
    return logging.getLogger(name)
