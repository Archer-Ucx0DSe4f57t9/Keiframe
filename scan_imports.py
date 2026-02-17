import os
import ast

def get_all_imports(directory):
    imports = set()
    # 获取 src 目录下的所有文件夹名，作为本地模块排除
    local_modules = {name for name in os.listdir(directory) if os.path.isdir(os.path.join(directory, name))}
    local_modules.add('src')

    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=path)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Import):
                                for n in node.names:
                                    imports.add(n.name.split('.')[0])
                            elif isinstance(node, ast.ImportFrom):
                                if node.module:
                                    imports.add(node.module.split('.')[0])
                except Exception as e:
                    print(f"读取文件 {path} 出错: {e}")

    # 排除 Python 自带的标准库 (简单过滤)
    std_libs = {'os', 'sys', 'time', 're', 'json', 'threading', 'logging', 'abc', 'typing', 'ast', 'datetime', 'math'}
    
    return imports - local_modules - std_libs

if __name__ == "__main__":
    found_imports = get_all_imports("./src")
    print("\n=== 你的项目依赖的第三方库清单 ===")
    for imp in sorted(found_imports):
        print(f"- {imp}")