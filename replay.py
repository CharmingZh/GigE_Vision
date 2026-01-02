"""
文件名称: replay.py (Optimized)
优化点:
1. 多进程并行处理：利用 CPU 多核加速图像转换和保存。
2. 颜色修正：修复保存时的 RGB/BGR 通道反转问题。
3. 模式分离：将批量转换和播放功能分开，互不干扰。
4. 元数据优化：直接读取 metadata.csv，避免遍历数万个文件的 IO 开销。
"""

import os
import numpy as np
import cv2
from concurrent.futures import ProcessPoolExecutor
import time

# === 配置 ===
INPUT_DIR = "C:/Yuyuan/Camera/Test/TTT/Source1"
OUTPUT_DIR = "C:/Yuyuan/Camera/Test/TTT/PIC/Source1"
PIXEL_TYPE_MONO8 = 0x01080001
PIXEL_TYPE_BAYERRG8 = 0x01080009

def process_single_frame(file_info):
    """
    单个文件的处理函数，设计为可以被多进程调用
    """
    bin_path, width, height, pixel_type, save_path = file_info
    
    try:
        with open(bin_path, 'rb') as f:
            raw = f.read()

        if pixel_type == PIXEL_TYPE_MONO8:
            image = np.frombuffer(raw, dtype=np.uint8).reshape((height, width))
            cv2.imwrite(save_path, image)
            
        elif pixel_type == PIXEL_TYPE_BAYERRG8:
            bayer = np.frombuffer(raw, dtype=np.uint8).reshape((height, width))
            # 注意：保存为图片时使用 BGR，否则颜色会反转
            image = cv2.cvtColor(bayer, cv2.COLOR_BayerRG2BGR)
            cv2.imwrite(save_path, image)
        else:
            return f"Unsupported pixel type: {pixel_type}"
            
        return None # Success
    except Exception as e:
        return f"Error processing {bin_path}: {str(e)}"

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 1. 读取 metadata.csv
    csv_path = os.path.join(INPUT_DIR, "metadata.csv")
    if not os.path.exists(csv_path):
        print(f"Error: metadata.csv not found in {INPUT_DIR}")
        print("Please run play_record.py first to generate data.")
        return

    tasks = []
    print("Reading metadata...")
    with open(csv_path, "r", encoding="utf-8") as f:
        header = f.readline() # 跳过表头
        for line in f:
            line = line.strip()
            if not line:
                continue
            # block_id,timestamp,width,height,pixel_type,payload_size,filename
            parts = line.split(",")
            if len(parts) < 7:
                continue
            
            try:
                width = int(parts[2])
                height = int(parts[3])
                pixel_type = int(parts[4])
                filename = parts[6]
                
                bin_path = os.path.join(INPUT_DIR, filename)
                save_name = filename.replace(".bin", ".bmp")
                save_path = os.path.join(OUTPUT_DIR, save_name)
                
                tasks.append((bin_path, width, height, pixel_type, save_path))
            except ValueError:
                continue

    print(f"Found {len(tasks)} frames.")

    if not tasks:
        print("No tasks found.")
        return

    # 3. 并行处理 (转换模式)
    print("Starting batch conversion (Parallel)...")
    start_time = time.time()
    
    # 使用 ProcessPoolExecutor 利用多核 CPU
    # chunksize 设置为 10 可以减少进程间通信开销
    with ProcessPoolExecutor() as executor:
        results = list(executor.map(process_single_frame, tasks, chunksize=10))

    # 统计结果
    errors = [r for r in results if r is not None]
    duration = time.time() - start_time
    print(f"Conversion finished in {duration:.2f}s. Errors: {len(errors)}")
    if errors:
        print("First 5 errors:", errors[:5])

    # 4. 播放模式 (可选)
    # 如果需要播放，读取刚刚生成的 BMP 文件（比实时解压 RAW 快得多）
    print("Starting playback...")
    cv2.namedWindow("Playback", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Playback", 800, 600)
    
    for task in tasks:
        save_path = task[4]
        if os.path.exists(save_path):
            img = cv2.imread(save_path)
            if img is not None:
                cv2.imshow("Playback", img)
                if cv2.waitKey(30) == 27:
                    break
    
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
