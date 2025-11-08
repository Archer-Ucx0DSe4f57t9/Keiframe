import csv
import os
import glob
import shutil

# 定义要添加到每行最后一列的固定值
APPEND_VALUE = "Default.mp3"
TEMP_SUFFIX = ".bak" # 用于创建临时备份文件

def append_column_to_csvs(directory="."):
    """
    遍历指定目录下的所有CSV文件，并在每行末尾添加一个固定值。

    :param directory: 要搜索CSV文件的目录路径，默认为当前目录。
    """
    print(f"开始在目录 '{directory}' 中处理所有CSV文件...")
    
    # 使用glob查找所有CSV文件
    csv_files = glob.glob(os.path.join(directory, "*.csv"))
    
    if not csv_files:
        print("未找到任何CSV文件。")
        return

    for filename in csv_files:
        print(f"\n正在处理文件: {filename}")
        
        # 创建一个临时文件路径用于写入更新后的内容
        temp_filename = filename + TEMP_SUFFIX
        
        try:
            # 1. 以只读模式打开原文件
            with open(filename, 'r', newline='', encoding='utf-8') as infile:
                reader = csv.reader(infile)
                
                # 2. 以写入模式打开临时文件
                with open(temp_filename, 'w', newline='', encoding='utf-8') as outfile:
                    writer = csv.writer(outfile)
                    
                    # 3. 逐行读取、修改并写入
                    for row in reader:
                        # 在当前行的末尾添加 APPEND_VALUE
                        row.append(APPEND_VALUE)
                        # 将修改后的行写入临时文件
                        writer.writerow(row)
            
            # 4. 替换原文件：先备份原文件（如果需要），然后将临时文件重命名为原文件名
            # 为了简化，我们直接用临时文件替换原文件
            os.replace(temp_filename, filename)
            print(f"文件 '{filename}' 处理完成，已添加 '{APPEND_VALUE}'。")
            
        except FileNotFoundError:
            print(f"错误: 找不到文件 {filename}")
        except Exception as e:
            print(f"处理文件 {filename} 时发生错误: {e}")
            # 尝试清理临时文件以防出错
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
                print(f"已清理临时文件: {temp_filename}")


if __name__ == "__main__":
    # 运行脚本，处理当前目录下的CSV文件
    append_column_to_csvs()
    print("\n所有CSV文件处理完毕。")