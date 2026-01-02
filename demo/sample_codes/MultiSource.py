"""
文件名称: MultiSource.py
功能描述:
    该脚本演示了如何从多源设备（Multi-Source Device）采集图像。
    它检测设备上的所有可用源（SourceSelector），并为每个源创建一个 `Source` 对象。
    每个 `Source` 对象管理自己的 `PvStream` 和 `PvPipeline`，实现并行采集。

特别注意事项:
    1. 脚本依赖 `opencv-python` (cv2) 进行图像显示（如果可用）。
    2. 演示了如何遍历 `SourceSelector` 枚举来发现所有源。
    3. 展示了多线程/多流管理的结构。
"""
#!/usr/bin/env python3

'''
 *****************************************************************************

     Copyright (c) 2022, Pleora Technologies Inc., All rights reserved.

 *****************************************************************************

 This sample shows how to receive images from a multi-source device using PvPipeline.
'''

import eBUS as eb
import lib.PvSampleUtils as psu

kb = psu.PvKb()

class Source:

    _BUFFER_COUNT = 16
    _DOODLE_LENGTH = 6
    _DOODLE = "|\\-|-/"

    _device = None
    _stream = None
    _pipeline = None
    _connection_id = None
    _source = None
    _doodle_index = 0

    def __init__(self, device, connection_id, source):
        self._device = device
        self._connection_id = connection_id
        self._source = source

    def Open(self):
        # 选择此源
        stack = eb.PvGenStateStack(self._device.GetParameters())
        self.SelectSource(stack)

        source_channel = 0
        if self._source:
            print("Reading source channel on device")
            result, source_channel = self._device.GetParameters().GetIntegerValue("SourceIDValue")
            if result.IsFailure():
                # 尝试使用已弃用的 SourceStreamChannel
                result, source_channel = self._device.GetParameters().GetIntegerValue("SourceStreamChannel")
            if result.IsFailure():
                return False

        print("Opening stream from device")
        # 显式检查 GEV 或 U3V 类型，这是配置通道所必需的
        if isinstance(self._device, eb.PvDeviceGEV):
            self._stream = eb.PvStreamGEV()
            if self._stream.Open(self._connection_id, 0, source_channel).IsFailure():
                print("Error opening stream to GigE Vision device")
                return False

            local_ip = self._stream.GetLocalIPAddress()
            local_port = self._stream.GetLocalPort()

            print("Setting source destination on device (channel", source_channel, ") to", local_ip, "port", local_port)
            self._device.SetStreamDestination(local_ip, local_port, source_channel)
        elif isinstance(self._device, eb.PvDeviceU3V):
            self._stream = eb.PvStreamU3V
            if self._stream.Open(self._connection_id, source_channel).IsFailure():
                print("Error opening stream to USB3 Vision Device")
                return False

        payload_size = self._device.GetPayloadSize()

        self._pipeline = eb.PvPipeline(self._stream)
        self._pipeline.SetBufferSize(payload_size)
        self._pipeline.SetBufferCount(self._BUFFER_COUNT)
        print("Starting pipeline thread")
        self._pipeline.Start()
        return True

    def Close(self):
        print("Closing source", self._source)

        print("Stopping pipeline thread")
        self._pipeline.Stop()

        print("Closing stream")
        self._stream.Close()

    def StartAcquisition(self):
        print("Start acquisition", self._source)
        stack = eb.PvGenStateStack(self._device.GetParameters())
        self.SelectSource(stack)

        self._device.StreamEnable()

        print("Sending AcquisitionStart command to device")
        self._device.GetParameters().Get("AcquisitionStart").Execute()

    def StopAcquisition(self):
        print("Stop acquisition", self._source)
        stack = eb.PvGenStateStack(self._device.GetParameters())
        self.SelectSource(stack)

        print("Sending AcquisitionStop command to device")
        self._device.GetParameters().Get("AcquisitionStop").Execute()

        self._device.StreamDisable()

    def RetrieveImages(self, timeout):
        while True:
            result, buffer, operational_result = self._pipeline.RetrieveNextBuffer(timeout)
            if result.IsFailure():
                return False
            
            self._doodle_index = self._doodle_index + 1
            self._doodle_index %= self._DOODLE_LENGTH
            
            self._pipeline.ReleaseBuffer(buffer)

    def GetStatistics(self, statistics):
        result, fps = self._stream.GetParameters().GetFloatValue("AcquisitionRate")

        result, bandwidth = self._stream.GetParameters().GetFloatValue("Bandwidth")
        bandwidth /= 1000000

        if self._source:
            return statistics + "{0} : {1} {2:.1f} FPS {3:.1f} Mb/s ".format(self._source, self._DOODLE[self._doodle_index], fps, bandwidth)
        else:
            return statistics + "{0} : {1} {2:.1f} FPS {3:.1f} Mb/s ".format("Source 0: ", self._DOODLE[self._doodle_index], fps, bandwidth)

    def GetRecommendedTimeout(self):
        result, fps = self._stream.GetParameters().GetFloatValue("AcquisitionRate")
        if fps == 0:
            return 1

        timeout = (1 / fps) * 1000
        timeout /= 2
        if timeout < 1:
            timeout = 1

        return timeout

    def SelectSource(self, stack):
        if self._source:
            stack.SetEnumValue("SourceSelector", self._source)


def AcquireImages():
    # 提示用户选择设备
    connection_id = psu.PvSelectDevice()
    if not connection_id:
        print("No device selected.")
        return False
    
    result, device = eb.PvDevice.CreateAndConnect(connection_id)
    if result.IsFailure():
        print("Unable to connect to device.")
        return False
    if not isinstance(device, eb.PvDeviceGEV):
        print("The selected device is not currently supported by this sample.")
        return False
    print("Successfully connected to device")

    sources = []
    source_selector = device.GetParameters().GetEnum("SourceSelector")
    # print(source_selector)
    if source_selector:
        # 获取所选设备上的所有源
        result, source_count = source_selector.GetEntriesCount()
        for source_index in range(source_count):
            result, source_entry = source_selector.GetEntryByIndex(source_index)
            if source_entry:
                result, source_name = source_entry.GetName()
                source = Source(device, connection_id, source_name)
                if source.Open():
                    sources.append(source)
    else:
        # 获取单个源
        source = Source(device, connection_id, "")
        if source.Open():
            sources.append(source)
    
    if len(sources) == 0:
            print("No source available.")
            return False

    for source in sources:
        source.StartAcquisition()

    # 检索图像
    timeout = 1
    new_timeout = 1000
    print("<press a key to stop streaming>")
    kb = psu.PvKb()
    kb.start()
    statistics = ""
    while not kb.is_stopping():
        for source in sources:
            source.RetrieveImages(timeout)
            statistics = source.GetStatistics(statistics)

            recommended_timeout = source.GetRecommendedTimeout()
            if recommended_timeout < new_timeout:
                new_timeout = recommended_timeout

        # 清除上一行，打印并重置统计信息
        print('\033[K', end='')
        print(statistics, end='\r')
        statistics = ""

        if kb.kbhit():
            kb.getch()
            break

    # 更新下一次执行的超时时间
    timeout = new_timeout / (len(sources) + 0.5)

    for source in sources:
        source.StopAcquisition()

    for source in sources:
        source.Close()

print("MultiSource sample")
print("Acquire images from a GigE Vision device")
AcquireImages()

print("<press a key to exit>")
kb.start()
kb.getch()
kb.stop()
