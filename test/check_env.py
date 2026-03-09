import sys
import importlib.util
import subprocess

def main():
    print("=" * 50)
    print(" JAI eBUS Python SDK 环境诊断工具")
    print("=" * 50)
    print(f"当前正在运行的 Python 解释器路径:\n {sys.executable}")
    print(f"当前 Python 版本:\n {sys.version}\n")
    
    # 1. 检查 ebus-python 包的文件结构
    print("--- 正在检查 ebus-python 包的具体文件 ---")
    try:
        # 使用 pip show -f 来查看安装的包里面到底包含哪些文件
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'show', '-f', 'ebus-python'], 
            capture_output=True, text=True
        )
        if "WARNING: Package(s) not found" in result.stderr:
            print("警告：当前的 Python 环境中并没有找到 ebus-python，请检查虚拟环境是否激活正确！")
        else:
            # 过滤输出，只打印 .py 或 .pyd 相关的文件，方便找模块名
            lines = result.stdout.split('\n')
            print("找到包信息，关键文件列表如下：")
            for line in lines:
                if '.py' in line or '.pyd' in line or 'Name:' in line or 'Location:' in line:
                    print(line.strip())
    except Exception as e:
        print(f"执行 pip show 失败: {e}")

    # 2. 测试可能的所有模块名
    print("\n--- 正在测试导入 ---")
    modules_to_try = ['ebus', 'ebus_python', 'pv', 'jaibus']
    success = False
    
    for mod in modules_to_try:
        try:
            importlib.import_module(mod)
            print(f"✅ 成功导入模块: '{mod}'！")
            print(f"   请在你的相机控制脚本中将 import ebus 修改为 import {mod}")
            success = True
            break
        except ModuleNotFoundError:
            print(f"❌ 尝试导入 '{mod}' 失败 (ModuleNotFoundError: 找不到该名称的模块)。")
        except ImportError as e:
            print(f"❌ 尝试导入 '{mod}' 失败 (ImportError: 模块存在但加载失败)。")
            print(f"   详细错误: {e}")
            print("   👉 这通常是因为缺少 Windows 底层的 JAI eBUS Runtime 相关的 .dll 依赖。请确认是否安装了 JAI Control Tool 或 eBUS Player。")
    
    if not success:
        print("\n诊断结束：所有常规模块名均导入失败。请仔细查看上方 '关键文件列表' 中的顶级文件夹或 .pyd 文件名称，那就是实际应该 import 的名字。")

if __name__ == "__main__":
    main()