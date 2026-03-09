import sys
import os
import cv2
import numpy as np

# 确保能找到 ebus 模块
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import eBUS as ebus

class CameraSource:
    def __init__(self, device, connection_id, source_name):
        self.device = device
        self.connection_id = connection_id
        self.source_name = source_name
        self.stream = None
        self.pipeline = None
        self.channel = 0

    def open(self):
        stack = ebus.PvGenStateStack(self.device.GetParameters())
        if self.source_name:
            stack.SetEnumValue("SourceSelector", self.source_name)
            res, self.channel = self.device.GetParameters().GetIntegerValue("SourceIDValue")
            if not res.IsOK():
                res, self.channel = self.device.GetParameters().GetIntegerValue("SourceStreamChannel")

        self.stream = ebus.PvStreamGEV()
        self.stream.Open(self.connection_id, 0, self.channel)
        self.device.SetStreamDestination(self.stream.GetLocalIPAddress(), self.stream.GetLocalPort(), self.channel)

        self.pipeline = ebus.PvPipeline(self.stream)
        self.pipeline.SetBufferSize(self.device.GetPayloadSize())
        self.pipeline.SetBufferCount(16)
        self.pipeline.Start()

    def start(self):
        if self.source_name:
            ebus.PvGenStateStack(self.device.GetParameters()).SetEnumValue("SourceSelector", self.source_name)
        self.device.StreamEnable()
        self.device.GetParameters().ExecuteCommand("AcquisitionStart")

    def stop(self):
        if self.source_name:
            ebus.PvGenStateStack(self.device.GetParameters()).SetEnumValue("SourceSelector", self.source_name)
        self.device.GetParameters().ExecuteCommand("AcquisitionStop")
        self.device.StreamDisable()

    def close(self):
        if self.pipeline: self.pipeline.Stop()
        if self.stream: 
            self.stream.Close()
            ebus.PvStream.Free(self.stream)

def main():
    system = ebus.PvSystem()
    system.Find()
    
    # 查找第一个设备
    device_info = next((system.GetInterface(i).GetDeviceInfo(j) 
                        for i in range(system.GetInterfaceCount()) 
                        for j in range(system.GetInterface(i).GetDeviceCount())), None)
    
    if not device_info:
        print("未找到设备")
        return

    res, device = ebus.PvDevice.CreateAndConnect(device_info)
    if not res.IsOK(): return

    sources = []
    selector = device.GetParameters().GetEnum("SourceSelector")
    if selector:
        res, count = selector.GetEntriesCount()
        for i in range(count):
            res, entry = selector.GetEntryByIndex(i)
            res, name = entry.GetName()
            src = CameraSource(device, device_info.GetConnectionID(), name)
            src.open()
            sources.append(src)
    else:
        src = CameraSource(device, device_info.GetConnectionID(), "")
        src.open()
        sources.append(src)

    for src in sources: src.start()
    print("开始采集... 按 'q' 退出")

    try:
        while True:
            for i, src in enumerate(sources):
                res, buffer, op_res = src.pipeline.RetrieveNextBuffer(100)
                if res.IsOK() and op_res.IsOK() and buffer.GetPayloadType() == ebus.PvPayloadTypeImage:
                    img = buffer.GetImage()
                    data = img.GetDataPointer()
                    
                    # 根据通道索引处理图像
                    if i == 0:
                        # Source 0: 可见光通道 (BayerRG8)
                        # 将 Bayer 格式转换为 BGR 彩色图像
                        try:
                            display_data = cv2.cvtColor(data, cv2.COLOR_BayerRG2RGB)
                            window_name = "Visible (RGB Color)"
                        except cv2.error:
                            display_data = data
                            window_name = "Visible (Raw)"
                    elif i == 1:
                        # Source 1: 近红外 1
                        display_data = data
                        window_name = "NIR 1"
                    elif i == 2:
                        # Source 2: 近红外 2
                        display_data = data
                        window_name = "NIR 2"
                    else:
                        display_data = data
                        window_name = f"Source {i}"

                    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
                    cv2.resizeWindow(window_name, 640, 480)
                    # 平铺窗口：可见光在左，两个近红外在右侧上下排列
                    if i == 0:
                        cv2.moveWindow(window_name, 100, 100)
                    elif i == 1:
                        cv2.moveWindow(window_name, 750, 100)
                    elif i == 2:
                        cv2.moveWindow(window_name, 750, 600)

                    cv2.imshow(window_name, display_data)
                    
                if res.IsOK():
                    src.pipeline.ReleaseBuffer(buffer)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    except KeyboardInterrupt:
        pass

    print("正在清理资源...")
    for src in sources:
        src.stop()
        src.close()
    device.Disconnect()
    ebus.PvDevice.Free(device)

if __name__ == "__main__":
    main()
