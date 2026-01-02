"""
文件名称: read_from_raw.py
功能描述: 
    该脚本用于从指定的输入目录读取原始图像数据（.bin文件）及其对应的元数据（.json文件）。
    它将原始数据解析为图像，支持 Mono8 和 BayerRG8 格式，并将处理后的图像保存为 BMP 文件。
    同时，它会弹出一个窗口播放处理后的图像序列。

特别注意事项:
    1. 请确保 `input_dir` 路径下包含成对的 .bin 和 .json 文件。
    2. `output_dir` 将用于保存生成的 BMP 图像，如果不存在会自动创建。
    3. 目前仅支持 PIXEL_TYPE_MONO8 和 PIXEL_TYPE_BAYERRG8 两种像素格式，其他格式会被跳过。
    4. 文件名格式预期包含下划线分隔的部分，以便提取 block_id 进行排序（例如 frame_123_timestamp.bin）。
"""

import os
import json
import numpy as np
import cv2

# === 配置路径 ===
# 输入目录：存放 .bin 和 .json 文件的文件夹路径
input_dir = "C:/Yuyuan/Camera/Test/TTT/Source1"
# 输出目录：存放转换后的 .bmp 图片的文件夹路径
output_dir = "C:/Yuyuan/Camera/Test/TTT/PIC/Source1"
# 如果输出目录不存在，则创建该目录
os.makedirs(output_dir, exist_ok=True)

# === 支持的像素类型 ===
# 定义 Mono8 像素类型的常量值
PIXEL_TYPE_MONO8 = 0x01080001
# 定义 BayerRG8 像素类型的常量值 (十进制: 17301513)
PIXEL_TYPE_BAYERRG8 = 0x01080009  # 17301513

# === 提取 block_id（用于排序） ===
def extract_blockid(filename):
    """
    从文件名中提取 block_id，用于文件排序。
    假设文件名格式为 "prefix_blockid_suffix.ext"。
    """
    try:
        # 使用 "_" 分割文件名，提取第二个部分（索引为1）并转换为整数
        return int(filename.split("_")[1])  # 提取中间的 X 并转为整数
    except (IndexError, ValueError):
        # 如果提取失败（例如文件名格式不符），返回 -1，使其排在最前面
        return -1  # 出错时默认排序在最前

# === 获取所有 .bin 文件，并按 block_id 排序 ===
# 遍历输入目录，筛选出所有以 .bin 结尾的文件
# 并使用 extract_blockid 函数作为 key 进行排序，确保按帧顺序处理
bin_files = sorted(
    [f for f in os.listdir(input_dir) if f.endswith(".bin")],
    key=extract_blockid
)

# 打印找到的文件数量
print(f"Found {len(bin_files)} frames")

# === 播放并保存图像循环 ===
# 遍历每一个排序后的 bin 文件
for bin_file in bin_files:
    # 构造 bin 文件的完整路径
    bin_path = os.path.join(input_dir, bin_file)
    # 构造对应的 json 元数据文件的路径（将 .bin 替换为 .json）
    meta_path = bin_path.replace(".bin", ".json")

    # 检查元数据文件是否存在
    if not os.path.exists(meta_path):
        print(f"[Missing meta] {meta_path}")
        continue  # 如果不存在，跳过此文件

    # 读取 json 元数据文件
    with open(meta_path, 'r') as f:
        meta = json.load(f)

    # 从元数据中提取图像的宽、高、像素类型和 block_id
    width = meta["width"]
    height = meta["height"]
    pixel_type = meta["pixel_type"]
    block_id = meta.get("block_id", "unknown")

    # 读取 bin 文件中的原始图像数据
    with open(bin_path, 'rb') as f:
        raw = f.read()

    image = None
    # 根据像素类型进行处理
    if pixel_type == PIXEL_TYPE_MONO8:
        # 如果是 Mono8，直接将二进制数据转换为 numpy 数组，并 reshape 为 (height, width)
        image = np.frombuffer(raw, dtype=np.uint8).reshape((height, width))
        # 构造保存路径
        save_path = os.path.join(output_dir, f"frame_{block_id}.bmp")
        # 保存图像
        cv2.imwrite(save_path, image)
    elif pixel_type == PIXEL_TYPE_BAYERRG8:
        # 如果是 BayerRG8，先转换为 numpy 数组
        bayer = np.frombuffer(raw, dtype=np.uint8).reshape((height, width))
        # 使用 OpenCV 将 BayerRG 转换为 RGB 图像
        image = cv2.cvtColor(bayer, cv2.COLOR_BayerRG2RGB)
        # 构造保存路径
        save_path = os.path.join(output_dir, f"frame_{block_id}.bmp")
        # 保存图像 (注意：OpenCV 默认保存为 BGR，如果 image 是 RGB，保存出来的颜色可能不对，
        # 但这里 cvtColor 转换为了 RGB，imwrite 期望 BGR。
        # 如果需要颜色正确，通常需要再转一次 RGB2BGR，或者直接转 BayerRG2BGR)
        # cv2.imwrite(save_path, cv2.cvtColor(image, cv2.COLOR_RGB2BGR))  # 保存为 BGR 格式
        cv2.imwrite(save_path, image)
    else:
        # 如果是不支持的像素类型，打印错误信息并跳过
        print(f"[Unsupported pixel type] {pixel_type}")
        continue

    # === 显示窗口 ===
    # 创建一个名为 "Playback" 的窗口，允许调整大小
    cv2.namedWindow("Playback", cv2.WINDOW_NORMAL)
    # 设置窗口大小为 800x600
    cv2.resizeWindow("Playback", 800, 600)
    # 在窗口中显示当前图像
    cv2.imshow("Playback", image)

    # 等待按键，延迟 30ms
    key = cv2.waitKey(30)
    if key == 27:  # 如果按下 ESC 键 (ASCII 27)
        break  # 退出循环

# 销毁所有 OpenCV 窗口
cv2.destroyAllWindows()
# 打印完成信息
print("Finished playback and saving.")
