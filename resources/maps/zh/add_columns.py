import pandas as pd
import os
import glob

def add_new_columns_to_csvs(new_col1_name='New_Column_1', new_col2_name='New_Column_2'):
    """
    遍历当前目录下所有CSV文件，并在每个文件末尾添加两个新的空列。
    
    参数:
        new_col1_name (str): 第一个新列的名称。
        new_col2_name (str): 第二个新列的名称。
    """
    # 使用 glob 查找当前目录下的所有 .csv 文件
    csv_files = glob.glob("*.csv")
    
    if not csv_files:
        print("在当前目录下没有找到任何 .csv 文件。")
        return

    print(f"找到 {len(csv_files)} 个 .csv 文件，开始处理...")
    
    for filename in csv_files:
        try:
            # 1. 读取 CSV 文件
            # encoding='utf-8' 是常见且推荐的，如果你的文件是其他编码，可能需要修改
            df = pd.read_csv(filename, encoding='utf-8')
            
            # 2. 检查新列是否已存在，防止重复添加
            if new_col1_name in df.columns or new_col2_name in df.columns:
                print(f"⚠️ 文件 '{filename}' 中已包含新列名，跳过添加。")
                continue

            # 3. 添加新的空列 (Pandas会自动用 NaN 填充)
            df[new_col1_name] = "" 
            df[new_col2_name] = ""
            
            # 4. 将修改后的 DataFrame 写回 CSV 文件
            # index=False 确保不将 DataFrame 的索引写入 CSV
            df.to_csv(filename, index=False, encoding='utf-8')
            
            print(f"✅ 成功处理文件: '{filename}'，已添加 '{new_col1_name}' 和 '{new_col2_name}' 两列。")

        except Exception as e:
            print(f"❌ 处理文件 '{filename}' 时发生错误: {e}")

# 运行函数
if __name__ == "__main__":
    add_new_columns_to_csvs()