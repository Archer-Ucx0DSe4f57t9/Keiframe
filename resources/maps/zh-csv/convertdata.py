import os
import shutil

def convert_map_files_to_csv(directory="."):
    """
    扫描指定目录下所有被视为地图文件的文件（无扩展名），
    将其内容中的 Tab 分隔符替换为 Comma，并保存为同名 .csv 文件。
    
    :param directory: 要扫描的目录路径。
    """
    print(f"--- 开始转换目录: {os.path.abspath(directory)} 中的地图文件 ---")
    
    converted_count = 0
    
    # 遍历当前目录下的所有文件和文件夹
    for entry in os.listdir(directory):
        full_path = os.path.join(directory, entry)
        
        # 仅处理文件且该文件没有扩展名（作为地图文件识别）
        if os.path.isfile(full_path) and not os.path.splitext(entry)[1]:
            try:
                # 1. 读取原始文件内容
                with open(full_path, 'r', encoding='utf-8') as f:
                    original_content = f.read()
                
                # 2. 替换所有 Tab 为 Comma
                # 注意：这里假设地图文件中的事件内容不会包含 Tab 或 Comma，如果包含，CSV格式需要更复杂的处理。
                new_content = original_content.replace('\t', ',')
                
                # 3. 构造新的 CSV 文件路径
                new_file_name = entry + ".csv"
                new_file_path = os.path.join(directory, new_file_name)
                
                # 4. 写入新文件
                with open(new_file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                print(f"✅ 成功转换: '{entry}' -> '{new_file_name}'")
                converted_count += 1
                
            except Exception as e:
                print(f"❌ 处理文件 '{entry}' 时出错: {e}")

    print(f"--- 转换完成，共转换 {converted_count} 个文件 ---")
    print("请手动检查生成的 .csv 文件内容，并更新您的代码以读取这些新文件。")


if __name__ == '__main__':
    # 你可以运行这个脚本，确保它在包含地图文件的目录中
    convert_map_files_to_csv()