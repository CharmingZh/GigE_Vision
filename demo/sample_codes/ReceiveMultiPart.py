"""
文件名称: ReceiveMultiPart.py
功能描述:
    该脚本演示了如何使用 `PvPipeline` 接收 Multi-Part 图像（例如 3D 相机数据）。
    Multi-Part Payload 包含多个部分（Parts），每个部分可以是图像、置信度图等。
    脚本展示了如何解析 Multi-Part 容器并显示其中的图像部分。

特别注意事项:
    1. 脚本依赖 `opencv-python` (cv2) 进行图像显示。
    2. 演示了 `PvMultiPartContainer` 的使用。
    3. 支持 Large Leader Trailer 模式（通过命令行参数 `-l` 或 `--large_leader_trailer` 启用）。
"""
#!/usr/bin/env python3

'''
 *****************************************************************************

     Copyright (c) 2022, Pleora Technologies Inc., All rights reserved.

 *****************************************************************************

 This sample shows how to receive images from a multi-part stream using PvPipeline.
'''

import eBUS as eb
import lib.PvSampleUtils as psu
import time
import sys, getopt

opencv_is_available = True
try:
    # 检测 OpenCV 是否可用
    import cv2
    opencv_version=cv2.__version__
except:
    opencv_is_available = False
    print("Warning: This sample requires python3-opencv to display a window")


class Source:

    _BUFFER_COUNT = 16
    _DEFAULT_FPS = 10
    _DOODLE_LENGTH = 6
    _DOODLE = "|\\-|-/"

    _device = None
    _stream = None
    _pipeline = None
    _connection_id = None
    _source = None
    _doodle_index = 0
    _stabilizer = eb.PvFPSStabilizer()
    _large_leader_trailer_enable = False

    def __init__(self, device, connection_id, source, large_leader_trailer = False):
        self._device = device
        self._connection_id = connection_id
        self._source = source
        self._stabilizer.Reset()
        self._large_leader_trailer_enable = large_leader_trailer

    def Open(self):
        # 选择此源
        stack = eb.PvGenStateStack(self._device.GetParameters())
        self.SelectSource(stack)

        print("Reading source channel on device")
        result, source_channel = self._device.GetParameters().GetIntegerValue("SourceIDValue")
        if result.IsFailure():
            # 尝试使用已弃用的 SourceStreamChannel
            result, source_channel = self._device.GetParameters().GetIntegerValue("SourceStreamChannel")
        if result.IsFailure():
            return False

        result = self._device.GetParameters().SetBooleanValue( "GevSCCFGMultiPartEnabled", True )
        if result.IsOK():
            if self._large_leader_trailer_enable:
                result = self._device.GetParameters().SetBooleanValue( "GevSCCFGLargeLeaderTrailerEnabled", True )
                if not result.IsOK():
                    print( "Cannot Enable Large Leader Trailer for the device" )
            else:
                self._device.GetParameters().SetBooleanValue( "GevSCCFGLargeLeaderTrailerEnabled", False )
        else:
            print( "Cannot Enable MultiPart Streaming for the device" )

        print("Opening stream from device") 
        # 显式检查 GEV 或 U3V 类型，这是配置通道所必需的
        if isinstance(self._device, eb.PvDeviceGEV):
            self._stream = eb.PvStreamGEV()
            if self._stream.Open(self._connection_id, 0, source_channel).IsFailure():
                print("Error opening stream to GigE Vision device")
                return False

            local_ip = self._stream.GetLocalIPAddress()
            local_port = self._stream.GetLocalPort()

            print(f"Setting source destination on device (channel {source_channel}) to {local_ip} port {local_port}")
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
        print("Closing source ", self._source)

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
        print("Stop acquisition ", self._source)
        stack = eb.PvGenStateStack(self._device.GetParameters())
        self.SelectSource(stack)

        print("Sending AcquisitionStop command to device")
        self._device.GetParameters().Get("AcquisitionStop").Execute()

        self._device.StreamDisable()

    def RetrieveImages(self, timeout):
        number_of_parts = 0
        is_multi_part = False
        result, buffer, operational_result = self._pipeline.RetrieveNextBuffer(timeout)
        if not result.IsOK():
            return False, result.GetCodeString()
        if buffer.GetPayloadType() == eb.PvPayloadTypeMultiPart:
            is_multi_part = True
            number_of_parts = buffer.GetMultiPartContainer().GetPartCount()
        if operational_result == eb.PV_OK and buffer.GetPayloadType() == eb.PvPayloadTypeMultiPart:

            while not self._stabilizer.IsTimeToDisplay(self._DEFAULT_FPS):
                time.sleep(0.0001)
            self.DisplayMultiPart(buffer)

            # 在这里，您通常会处理或操作图像

            self._doodle_index = self._doodle_index + 1
            self._doodle_index %= self._DOODLE_LENGTH

        self._pipeline.ReleaseBuffer(buffer)
        timeout = 0
        return is_multi_part, number_of_parts

    def GetStatistics(self, statistics, ismultipart, parts):
        result_fps, fps = self._stream.GetParameters().GetFloatValue("AcquisitionRate")
        result_bandwidth, bandwidth = self._stream.GetParameters().GetFloatValue("Bandwidth")
        bandwidth /= 1000000

        if result_fps.IsOK() and result_bandwidth.IsOK():
            statistics += "{0} : {1} {2:.1f} FPS {3:.1f} Mb/s".format(self._source, self._DOODLE[self._doodle_index], fps, bandwidth)
            if type(parts) is not int:
                statistics += " with Error {0}".format(parts)
            elif ismultipart:
                statistics += " with {0} parts".format(parts)
            return statistics
        else:
            return ""

    def GetRecommendedTimeout(self):
        result, fps = self._stream.GetParameters().GetFloatValue("AcquisitionRate")
        if result.IsFailure() or fps == 0:
            return 1

        timeout = (1 / fps) * 1000
        timeout /= 2
        if timeout < 1:
            timeout = 1

        return timeout

    def SelectSource(self, stack):
        if self._source:
            stack.SetEnumValue("SourceSelector", self._source)

    def DisplayMultiPart(self, buffer):
        part_container = buffer.GetMultiPartContainer()
        for part_index in range(part_container.GetPartCount()):
            section = part_container.GetPart(part_index)
            datatype = section.GetDataType()
            if eb.PvMultiPart2DImage <= datatype <= eb.PvMultiPartConfidenceMap:
                image = section.GetImage()
                image_data = image.GetDataPointer()

                if opencv_is_available:
                    cv2.imshow("part_" + str(part_index), image_data)
                    if cv2.waitKey(1) & 0xFF != 0xFF:
                        break

def AcquireImages(argv):
    large_leader_trailer = False
    if len(argv) > 1:
        if argv[1] in ("-l", "--large_leader_trailer"):
            print ('Attempt to Receive MultiPart Large Leader Trailer Images...')
            large_leader_trailer = True
        else:
            print ('Error: Unknown python arguments, plese use -l or --large_leader_trailer to enable MultiPart Large Leader Trailer feature')

    # 提示用户选择设备
    connection_id = psu.PvSelectDevice()
    if not connection_id:
        print("No device selected.")
        return False
    
    result, device = eb.PvDevice.CreateAndConnect(connection_id)
    if result.IsFailure():
        print("Unable to connect to device.")
        return False
    print("Successfully connected to device")

    sources = []
    source_selector = device.GetParameters().GetEnum("SourceSelector")
    if source_selector:
        # 获取所选设备上的所有源
        result, source_count = source_selector.GetEntriesCount()
        if result.IsFailure():
            return False
        for source_index in range(source_count):
            result, source_entry = source_selector.GetEntryByIndex(source_index)
            if result.IsFailure():
                return False
            if source_entry:
                result, source_name = source_entry.GetName()
                if result.IsFailure():
                    return False
                source = Source(device, connection_id, source_name, large_leader_trailer)
                if source.Open():
                    sources.append(source)
    else:
        # 获取单个源
        source = Source(device, connection_id, "", large_leader_trailer)
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
            is_multipart, parts_number = source.RetrieveImages(timeout)
            statistics = source.GetStatistics(statistics, is_multipart, parts_number)

            recommended_timeout = source.GetRecommendedTimeout()
            if recommended_timeout < new_timeout:
                new_timeout = recommended_timeout

        # 清除上一行，打印并重置统计信息
        sys.stdout.write("\033[K")
        print('\033[K', end='')
        print(statistics, end='\r')
        statistics = ""

        if kb.kbhit():
            kb.getch()
            break

    if opencv_is_available:
        cv2.destroyAllWindows()

    # 更新下一次执行的超时时间
    timeout = new_timeout / (len(sources) + 0.5)

    for source in sources:
        source.StopAcquisition()

    for source in sources:
        source.Close()

print("ReceiveMultiPart sample")
print("Acquire images from a multi-part stream")
AcquireImages(sys.argv[0:])
