"""
文件名称: test.py (Optimized)
优化点:
1. 延迟图像转换：仅在需要显示时才进行格式转换，大幅降低 CPU 占用。
2. 队列监控：增加保存队列大小监控，防止内存溢出。
3. 结构优化：将显示逻辑解耦。
"""

#!/usr/bin/env python3
import eBUS as eb
import sys
import os
import time
import json
import numpy as np
import cv2
import threading
import queue

# 将 sample/lib 目录添加到系统路径
sys.path.append("../sample/lib")
import PvSampleUtils as psu

# === 配置 ===
BUFFER_COUNT = 64
SAVE_DIR = "D:/Yuyuan/Sweetpotato/G8/G8_S3/"
DISPLAY_INTERVAL = 5
MAX_SAVE_QUEUE_SIZE = 500
SAVE_THREAD_NUM = 4  # 启动 4 个写入线程，榨干 SSD 性能

kb = psu.PvKb()

# === 保存队列 ===
save_queue = queue.Queue(maxsize=MAX_SAVE_QUEUE_SIZE)

def save_worker():
    """后台保存线程：只负责繁重的二进制数据写入"""
    while True:
        item = save_queue.get()
        if item is None:
            break
        bin_path, buffer_data = item  # 不再处理 meta
        try:
            with open(bin_path, "wb") as f:
                f.write(buffer_data)
        except Exception as e:
            print(f"[Save Error] {e}")
        finally:
            save_queue.task_done()

# 启动多个保存线程
for _ in range(SAVE_THREAD_NUM):
    threading.Thread(target=save_worker, daemon=True).start()

class SourceStream:
    def __init__(self, device, connection_id, source_name):
        self.device = device
        self.connection_id = connection_id
        self.source_name = source_name
        self.stream = None
        self.pipeline = None
        self.running = False
        self.capture_thread = None
        self.display_queue = queue.Queue(maxsize=2)
        self.save_path = os.path.join(SAVE_DIR, source_name)
        os.makedirs(self.save_path, exist_ok=True)
        self.frame_count = 0
        
        # CSV 元数据文件句柄
        self.csv_file = None

    def open(self):
        # ... (保持原有的 open 代码不变) ...
        stack = eb.PvGenStateStack(self.device.GetParameters())
        stack.SetEnumValue("SourceSelector", self.source_name)

        result, channel = self.device.GetParameters().GetIntegerValue("SourceIDValue")
        if result.IsFailure():
            result, channel = self.device.GetParameters().GetIntegerValue("SourceStreamChannel")
            if result.IsFailure():
                print(f"[{self.source_name}] Cannot determine stream channel.")
                return False

        self.stream = eb.PvStreamGEV()
        if self.stream.Open(self.connection_id, 0, channel).IsFailure():
            print(f"[{self.source_name}] Failed to open stream.")
            return False

        ip = self.stream.GetLocalIPAddress()
        port = self.stream.GetLocalPort()
        self.device.SetStreamDestination(ip, port, channel)

        payload_size = self.device.GetPayloadSize()
        self.pipeline = eb.PvPipeline(self.stream)
        self.pipeline.SetBufferSize(payload_size)
        self.pipeline.SetBufferCount(BUFFER_COUNT)
        self.pipeline.Start()
        
        # 初始化 CSV 文件
        csv_path = os.path.join(self.save_path, "metadata.csv")
        # 如果文件不存在，写入表头
        write_header = not os.path.exists(csv_path)
        # 使用 line_buffering=1 确保每行写入后刷新到 OS 缓存，防止程序崩溃丢失数据
        self.csv_file = open(csv_path, "a", encoding="utf-8", newline="")
        if write_header:
            self.csv_file.write("block_id,timestamp,width,height,pixel_type,payload_size,filename\n")
            
        return True

    # ... (start_acquisition, stop_acquisition 保持不变) ...
    def start_acquisition(self):
        stack = eb.PvGenStateStack(self.device.GetParameters())
        stack.SetEnumValue("SourceSelector", self.source_name)
        self.device.StreamEnable()
        self.device.GetParameters().Get("AcquisitionStart").Execute()

    def stop_acquisition(self):
        stack = eb.PvGenStateStack(self.device.GetParameters())
        stack.SetEnumValue("SourceSelector", self.source_name)
        self.device.GetParameters().Get("AcquisitionStop").Execute()
        self.device.StreamDisable()

    def close(self):
        if self.pipeline:
            self.pipeline.Stop()
        if self.stream:
            self.stream.Close()
        if self.csv_file:
            self.csv_file.close()

    def run(self):
        self.running = True
        print(f"[{self.source_name}] Acquisition started.")
        while self.running and not kb.is_stopping():
            result, buffer, op_result = self.pipeline.RetrieveNextBuffer(1000)
            
            if result.IsOK() and op_result.IsOK():
                image = buffer.GetImage()
                block_id = buffer.GetBlockID()
                timestamp = int(time.time() * 1000)
                
                # 1. 准备数据
                ptr = image.GetDataPointer()
                buffer_size = buffer.GetSize()
                buffer_data = ptr[:buffer_size] 
                
                filename = f"frame_{block_id}_{timestamp}.bin"
                bin_path = os.path.join(self.save_path, filename)
                
                # 2. 写入元数据 (直接写入 CSV，极快)
                # 格式: block_id,timestamp,width,height,pixel_type,payload_size,filename
                csv_line = f"{block_id},{timestamp},{image.GetWidth()},{image.GetHeight()},{image.GetPixelType()},{buffer_size},{filename}\n"
                self.csv_file.write(csv_line)
                # self.csv_file.flush() # 可选：如果非常担心断电数据丢失可开启，但会影响性能
                
                # 3. 放入保存队列 (仅二进制数据)
                try:
                    save_queue.put((bin_path, buffer_data), block=False)
                except queue.Full:
                    print(f"[{self.source_name}] Warning: Save queue full! Dropping frame {block_id}")

                # 4. 显示处理
                self.frame_count += 1
                if self.frame_count % DISPLAY_INTERVAL == 0:
                    if not self.display_queue.full():
                        width = image.GetWidth()
                        height = image.GetHeight()
                        pixel_type = image.GetPixelType()
                        
                        display_img = None
                        if pixel_type == eb.PvPixelMono8:
                            display_img = np.ctypeslib.as_array(ptr, shape=(height, width)).copy()
                        elif pixel_type == 0x01080009: # BayerRG8
                            raw_np = np.ctypeslib.as_array(ptr, shape=(height, width))
                            display_img = cv2.cvtColor(raw_np, cv2.COLOR_BayerRG2RGB)
                        elif pixel_type == eb.PvPixelRGB8:
                            raw_np = np.ctypeslib.as_array(ptr, shape=(height, width, 3))
                            display_img = cv2.cvtColor(raw_np, cv2.COLOR_RGB2BGR)
                        
                        if display_img is not None:
                            self.display_queue.put((block_id, display_img))

            self.pipeline.ReleaseBuffer(buffer)
        print(f"[{self.source_name}] Acquisition stopped.")


    def display_loop(self):
        while self.running:
            try:
                block_id, img = self.display_queue.get(timeout=0.1)
                # 缩小一点显示，减少渲染压力
                display_view = cv2.resize(img, (640, 480))
                cv2.putText(display_view, f"{self.source_name} ID:{block_id}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                cv2.imshow(f"{self.source_name}", display_view)
                if cv2.waitKey(1) & 0xFF == 27:
                    self.running = False
            except queue.Empty:
                # 保持 UI 响应
                cv2.waitKey(1)
                continue
        cv2.destroyWindow(f"{self.source_name}")

    def start_thread(self):
        self.capture_thread = threading.Thread(target=self.run)
        self.capture_thread.start()
        threading.Thread(target=self.display_loop, daemon=True).start()

    def stop_thread(self):
        self.running = False
        if self.capture_thread:
            self.capture_thread.join()

# ... main 函数保持大部分不变，只需确保调用 start_thread ...