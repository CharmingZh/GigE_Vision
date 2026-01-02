"""
文件名称: test.py
功能描述:
    该脚本演示了如何使用 eBUS SDK 连接 GigE 相机设备，并从多个源（Source）同时采集图像数据。
    它实现了以下主要功能：
    1. 连接设备并配置全局参数（如采集模式、帧率等）。
    2. 枚举设备支持的所有源（Source），并为每个源创建一个采集流（SourceStream）。
    3. 使用多线程分别从每个源获取图像数据。
    4. 将采集到的原始数据（.bin）和元数据（.json）异步保存到磁盘。
    5. 实时显示采集到的图像（每隔一定帧数刷新一次）。

特别注意事项:
    1. 需要安装 eBUS SDK 的 Python 绑定，并确保 `eBUS` 模块可用。
    2. 脚本依赖 `../sample/lib` 目录下的 `PvSampleUtils` 库，请确保路径正确。
    3. `SAVE_DIR` 变量定义了数据保存的根目录，请根据实际情况修改。
    4. 脚本默认配置了 "Source0", "Source1", "Source2" 的参数，请确保相机支持这些源。
    5. 按 ESC 键可以停止采集并退出程序。
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

# 将 sample/lib 目录添加到系统路径，以便导入 PvSampleUtils
sys.path.append("../sample/lib")
import PvSampleUtils as psu

# 定义缓冲区数量
BUFFER_COUNT = 512
# 定义数据保存目录
SAVE_DIR = "D:/Yuyuan/Sweetpotato/G8/G8_S3/"
# 初始化键盘监听工具
kb = psu.PvKb()

# === 保存队列线程 ===
# 创建一个队列用于存放待保存的数据，实现异步保存，避免阻塞采集线程
save_queue = queue.Queue()

def save_worker():
    """
    后台线程函数，用于从 save_queue 中获取数据并写入磁盘。
    """
    while True:
        # 从队列中获取一个项目
        item = save_queue.get()
        # 如果获取到 None，表示接收到停止信号，退出循环
        if item is None:
            break
        # 解包数据：bin文件路径，meta文件路径，二进制数据，元数据字典
        bin_path, meta_path, buffer_data, meta = item
        try:
            # 将二进制数据写入 .bin 文件
            with open(bin_path, "wb") as f:
                f.write(buffer_data)
            # 将元数据写入 .json 文件
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=4)
        except Exception as e:
            # 捕获并打印保存过程中的错误
            print(f"[Save Error] {e}")
        # 标记该任务已完成
        save_queue.task_done()

# 启动保存线程，设置为守护线程（daemon=True），主程序退出时自动结束
threading.Thread(target=save_worker, daemon=True).start()

class SourceStream:
    """
    管理单个图像源（Source）的流、管道和采集线程的类。
    """
    def __init__(self, device, connection_id, source_name):
        self.device = device
        self.connection_id = connection_id
        self.source_name = source_name
        self.stream = None
        self.pipeline = None
        self.running = False
        self.capture_thread = None
        # 用于显示的队列，限制大小以避免积压
        self.display_queue = queue.Queue(maxsize=5)
        # 为每个源创建一个独立的保存子目录
        self.save_path = os.path.join(SAVE_DIR, source_name)
        os.makedirs(self.save_path, exist_ok=True)

        self.frame_count = 0
        self.display_interval = 5  # 每 5 帧更新一次显示

    def open(self):
        """
        打开流并配置管道。
        """
        # 使用 PvGenStateStack 临时切换参数上下文
        stack = eb.PvGenStateStack(self.device.GetParameters())
        # 设置 SourceSelector 为当前源名称，以便获取该源的参数
        stack.SetEnumValue("SourceSelector", self.source_name)

        # 尝试获取 SourceIDValue
        result, channel = self.device.GetParameters().GetIntegerValue("SourceIDValue")
        if result.IsFailure():
            # 如果失败，尝试获取 SourceStreamChannel
            result, channel = self.device.GetParameters().GetIntegerValue("SourceStreamChannel")
            if result.IsFailure():
                print(f"[{self.source_name}] Cannot determine stream channel.")
                return False

        # 创建 PvStreamGEV 对象
        self.stream = eb.PvStreamGEV()
        # 打开流：使用连接ID和通道号
        if self.stream.Open(self.connection_id, 0, channel).IsFailure():
            print(f"[{self.source_name}] Failed to open stream.")
            return False

        # 获取本地 IP 和端口
        ip = self.stream.GetLocalIPAddress()
        port = self.stream.GetLocalPort()
        # 配置设备将流发送到此 IP 和端口
        self.device.SetStreamDestination(ip, port, channel)

        # 获取 PayloadSize（图像数据大小）
        payload_size = self.device.GetPayloadSize()
        # 创建 PvPipeline 用于管理缓冲区
        self.pipeline = eb.PvPipeline(self.stream)
        # 设置缓冲区大小
        self.pipeline.SetBufferSize(payload_size)
        # 设置缓冲区数量
        self.pipeline.SetBufferCount(BUFFER_COUNT)
        # 启动管道（开始预分配缓冲区）
        self.pipeline.Start()

        return True

    def start_acquisition(self):
        """
        开始采集。
        """
        # 切换参数上下文到当前源
        stack = eb.PvGenStateStack(self.device.GetParameters())
        stack.SetEnumValue("SourceSelector", self.source_name)
        # 启用流
        self.device.StreamEnable()
        # 执行 AcquisitionStart 命令
        self.device.GetParameters().Get("AcquisitionStart").Execute()

    def stop_acquisition(self):
        """
        停止采集。
        """
        # 切换参数上下文到当前源
        stack = eb.PvGenStateStack(self.device.GetParameters())
        stack.SetEnumValue("SourceSelector", self.source_name)
        # 执行 AcquisitionStop 命令
        self.device.GetParameters().Get("AcquisitionStop").Execute()
        # 禁用流
        self.device.StreamDisable()

    def close(self):
        """
        关闭管道和流。
        """
        if self.pipeline:
            self.pipeline.Stop()
        if self.stream:
            self.stream.Close()

    def run(self):
        """
        采集线程的主循环。
        """
        self.running = True
        while self.running and not kb.is_stopping():
            # 从管道中获取下一个缓冲区，超时时间 1000ms
            result, buffer, op_result = self.pipeline.RetrieveNextBuffer(1000)
            if result.IsOK() and op_result.IsOK():
                # 获取图像接口
                image = buffer.GetImage()
                if image:
                    width, height = image.GetWidth(), image.GetHeight()
                    pixel_type = image.GetPixelType()
                    ptr = image.GetDataPointer()
                    block_id = buffer.GetBlockID()
                    timestamp = int(time.time() * 1000)

                    # 构造保存路径
                    bin_path = os.path.join(self.save_path, f"frame_{block_id}_{timestamp}.bin")
                    meta_path = bin_path.replace(".bin", ".json")
                    # 获取缓冲区数据（切片）
                    buffer_data = ptr[:buffer.GetSize()]
                    # 构造元数据
                    meta = {
                        "block_id": int(block_id),
                        "timestamp": timestamp,
                        "width": width,
                        "height": height,
                        "pixel_type": int(pixel_type),
                        "payload_size": int(buffer.GetSize())
                    }
                    # 将数据放入保存队列
                    save_queue.put((bin_path, meta_path, buffer_data, meta))

                    # 处理图像用于显示
                    np_image = None
                    if pixel_type == eb.PvPixelMono8:
                        # Mono8 格式转换
                        np_image = np.ctypeslib.as_array(ptr, shape=(height, width)).copy()
                    elif pixel_type == 0x01080009:  # BayerRG8
                        # BayerRG8 格式转换
                        bayer = np.ctypeslib.as_array(ptr, shape=(height, width)).copy()
                        np_image = cv2.cvtColor(bayer, cv2.COLOR_BayerRG2RGB)
                    elif pixel_type == eb.PvPixelRGB8:
                        # RGB8 格式转换
                        np_image = np.ctypeslib.as_array(ptr, shape=(height, width, 3)).copy()
                        np_image = cv2.cvtColor(np_image, cv2.COLOR_RGB2BGR)

                    # 计数并决定是否更新显示
                    # self.frame_count += 1
                    # if self.frame_count % self.display_interval == 0 and np_image is not None:
                    #     self.display_queue.put((block_id, np_image))

            # 释放缓冲区回管道
            self.pipeline.ReleaseBuffer(buffer)

    def display_loop(self):
        """
        显示线程的主循环。
        """
        while self.running:
            try:
                # 从显示队列获取图像，超时 0.5s
                block_id, img = self.display_queue.get(timeout=0.5)
                # 在图像上绘制源名称和 Block ID
                cv2.putText(img, f"{self.source_name} - ID: {block_id}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                # 显示图像
                cv2.imshow(f"{self.source_name}", img)
                # 检查按键，如果是 ESC 则停止
                if cv2.waitKey(1) & 0xFF == 27:
                    self.running = False
            except queue.Empty:
                continue

    def start_thread(self):
        """
        启动采集线程和显示线程。
        """
        self.capture_thread = threading.Thread(target=self.run)
        self.capture_thread.start()
        threading.Thread(target=self.display_loop, daemon=True).start()

    def stop_thread(self):
        """
        停止线程。
        """
        self.running = False
        if self.capture_thread:
            self.capture_thread.join()

def main():
    print("▶ Streaming from multiple sources. Press ESC to stop.")
    # 选择设备
    connection_id = psu.PvSelectDevice()
    if not connection_id:
        return

    # 连接设备
    result, device = eb.PvDevice.CreateAndConnect(connection_id)
    if result.IsFailure():
        print("❌ Failed to connect to device.")
        return

    # === 全局参数设置 ===
    params = device.GetParameters()
    # 设置采集模式为连续
    params.Get("AcquisitionMode").SetValue("Continuous")
    # 关闭触发模式
    params.Get("TriggerMode").SetValue("Off")
    # 设置采集帧率
    params.Get("AcquisitionFrameRate").SetValue(30)

    # 为每个源设置曝光时间
    for name in ["Source0", "Source1", "Source2"]:
        params.Get("SourceSelector").SetValue(name)
        params.Get("ExposureTime").SetValue(5000)

    # === 枚举并打开源 ===
    sources = []
    # 获取 SourceSelector 枚举参数
    selector = device.GetParameters().GetEnum("SourceSelector")
    result, count = selector.GetEntriesCount()
    # 遍历所有源
    for i in range(count):
        result, entry = selector.GetEntryByIndex(i)
        if result.IsOK() and entry:
            result, name = entry.GetName()
            if result.IsOK():
                # 为每个源创建 SourceStream 对象
                stream = SourceStream(device, connection_id, name)
                # 尝试打开流
                if stream.open():
                    sources.append(stream)

    if not sources:
        print("❌ No source streams opened.")
        return
    print("\n⏹ Starting all streams...")
    # 启动所有流的采集和线程
    for s in sources:
        s.start_acquisition()
        s.start_thread()

    # 启动键盘监听
    kb.start()
    # 等待按键
    while not kb.kbhit():
        time.sleep(0.1)
    kb.getch()
    kb.stop()

    print("\n⏹ Stopping all streams...")
    # 停止所有流
    for s in sources:
        s.stop_thread()
        s.stop_acquisition()
        s.close()

    # 发送停止信号给保存线程
    save_queue.put(None)  # Stop save worker
    time.sleep(1)
    # 销毁所有窗口
    cv2.destroyAllWindows()

    print("✅ Done.")
    # 断开设备连接
    device.Disconnect()
    eb.PvDevice.Free(device)

if __name__ == "__main__":
    main()
