import os
import sys
from src.utils.logging_util import get_logger, setup_logger
logger = get_logger(__name__)

def get_project_root():
    """
    获取项目根目录：
    - 源码运行：main.py 的上一级目录
    - exe 运行：exe 文件所在目录
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后的 exe
        return os.path.dirname(sys.executable)
    else:
        # 源码运行，假设 main.py 在项目根目录下一级
        main_path = os.path.abspath(sys.modules['__main__'].__file__)
        return os.path.dirname(os.path.dirname(main_path))


def get_resources_dir(*subdirs):
    """
    获取项目根目录下的 resources 目录（支持子目录）
    """
    project_root = get_project_root()
    resources_dir = os.path.join(project_root, 'resources', *subdirs)

    if not os.path.exists(resources_dir):
        logger.error(f'资源目录不存在: {resources_dir}')
        return None

    logger.info(f'使用资源目录: {resources_dir}')
    return resources_dir

def list_files(directory):
    """
    列出指定目录下的所有文件
    :param directory: 目录路径
    :return: 文件列表
    """
    if not directory or not os.path.exists(directory):
        return []
    
    return [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]

def get_file_path(directory, filename):
    """
    获取文件的完整路径
    :param directory: 目录路径
    :param filename: 文件名
    :return: 文件的完整路径
    """
    if not directory or not filename:
        return None
    
    return os.path.join(directory, filename)