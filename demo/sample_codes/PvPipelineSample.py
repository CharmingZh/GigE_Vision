"""
文件名称: PvPipelineSample.py
功能描述:
    该脚本演示了如何使用 `PvPipeline` 对象从 GigE Vision 或 USB3 Vision 设备采集图像。
    `PvPipeline` 简化了缓冲区管理（分配、排队、检索、释放）。
    脚本还展示了如何处理不同类型的 Payload（图像、ChunkData、RawData、MultiPart、PleoraCompressed）。
    对于 Pleora 压缩格式，它演示了如何使用 `PvDecompressionFilter` 进行解压。

特别注意事项:
    1. 脚本依赖 `opencv-python` (cv2) 进行图像显示。
    2. 演示了 `PvPipelineEventSink` 的使用（通过 `my_pipeline_event_sink` 类）。
    3. 处理了多种 Payload 类型，是理解 eBUS SDK 数据接收的良好示例。
"""
#!/usr/bin/env python3

'''
*****************************************************************************
*
*   Copyright (c) 2020, Pleora Technologies Inc., All rights reserved.
*
*****************************************************************************

Shows how to use a PvPipeline object to acquire images from a GigE Vision or
USB3 Vision device.
'''

import numpy as np
import eBUS as eb
import lib.PvSampleUtils as psu

BUFFER_COUNT=16

kb = psu.PvKb()

opencv_is_available=True
register_events=False # 更改为 True 以查看事件信息
try:
    # 检测 OpenCV 是否可用
    import cv2
    opencv_version=cv2.__version__
except:
    opencv_is_available=False
    print("Warning: This sample requires python3-opencv to display a window")

class my_pipeline_event_sink(eb.PvPipelineEventSink):
    def OnBufferCreated(self, pipeline, pvbuffer):
        print(f"Buffer created.")
    def OnStart(self, pipeline):
        print("About to start.")
    def OnStop(self, pipeline):
        print("Just stopped")

def connect_to_device(connection_ID) :
    # 连接到 GigE Vision 或 USB3 Vision 设备
    print("Connecting to device.")
    result, device = eb.PvDevice.CreateAndConnect(connection_ID)
    if device == None :
        print(f"Unable to connect to device: {result.GetCodeString()} ({result.GetDescription()})")
    return device

def open_stream(connection_ID) :
    # 打开到 GigE Vision 或 USB3 Vision 设备的流
    print("Opening stream from device.")
    result, stream = eb.PvStream.CreateAndOpen(connection_ID)
    if stream == None :
        print(f"Unable to stream from device. {result.GetCodeString()} ({result.GetDescription()})")
    return stream

def configure_stream(device, stream) :
    # 如果是 GigE Vision 设备，配置 GigE Vision 特定的流参数
    if isinstance(device, eb.PvDeviceGEV) :
        # 协商数据包大小
        device.NegotiatePacketSize()
        # 配置设备流传输目标
        device.SetStreamDestination(stream.GetLocalIPAddress(), stream.GetLocalPort())

def create_pipeline(device, stream):
    # 创建 PvPipeline 对象
    pipeline = eb.PvPipeline(stream)

    if pipeline:
        # 从设备读取 Payload Size (图像大小)
        lSize = device.GetPayloadSize()
    
        # 设置缓冲区数量和缓冲区大小
        pipeline.SetBufferCount(BUFFER_COUNT)
        pipeline.SetBufferSize(lSize)
    
    return pipeline

def acquire_images(device, stream, pipeline):
    # 获取控制流所需的设备参数
    device_params = device.GetParameters()

    # 映射 GenICam AcquisitionStart 和 AcquisitionStop 命令
    start = device_params.Get("AcquisitionStart")
    stop = device_params.Get("AcquisitionStop")

    # 注意：必须在开始采集之前初始化管道
    print("Starting pipeline")
    pipeline.Start()

    # 获取流参数
    stream_params = stream.GetParameters()

    # 映射一些 GenICam 流统计计数器
    frame_rate = stream_params.Get("AcquisitionRate")
    bandwidth = stream_params[ "Bandwidth" ]

    # 启用流并发送 AcquisitionStart 命令
    print("Enabling streaming and sending AcquisitionStart command.")
    device.StreamEnable()
    start.Execute()

    doodle = "|\\-|-/"
    doodle_index = 0
    display_image = False
    warning_issued = False
    frame_rate_val = frame_rate.GetValue()
    bandwidth_val = bandwidth.GetValue()
    errors = 0
    decompression_filter = eb.PvDecompressionFilter()

    # 获取图像直到用户指示停止。
    print("\n<press a key to stop streaming>")
    kb.start()
    while not kb.is_stopping():
        # 检索下一个 pvbuffer，超时 1000ms
        result, pvbuffer, operational_result = pipeline.RetrieveNextBuffer(1000)
        if result.IsOK():
            if operational_result.IsOK():
                #
                # 我们现在有一个有效的 pvbuffer。这是您通常处理 pvbuffer 的地方。
                # -----------------------------------------------------------------------------------------
                # ...

                result, frame_rate_val = frame_rate.GetValue()
                result, bandwidth_val = bandwidth.GetValue()

                print(f"{doodle[doodle_index]} BlockID: {pvbuffer.GetBlockID():016d}", end='')

                image = None

                lPayloadType = pvbuffer.GetPayloadType()
                if lPayloadType == eb.PvPayloadTypeImage:
                    image = pvbuffer.GetImage()
                    
                elif lPayloadType == eb.PvPayloadTypeChunkData:
                    print(f" Chunk Data payload type with {pvbuffer.GetChunkCount()} chunks", end='')

                elif lPayloadType == eb.PvPayloadTypeRawData:
                    print(f" Raw Data with {pvbuffer.GetRawData().GetPayloadLength()} bytes", end='')

                elif lPayloadType == eb.PvPayloadTypeMultiPart:
                    print(f" Multi Part with {pvbuffer.GetMultiPartContainer().GetPartCount()} parts", end='')

                elif lPayloadType == eb.PvPayloadTypePleoraCompressed:
                    if eb.PvDecompressionFilter.IsCompressed(pvbuffer):
                        result, pixel_type, width, height = eb.PvDecompressionFilter.GetOutputFormatFor(pvbuffer)
                        if result.IsOK():
                            calculated_size = eb.PvImage.GetPixelSize(pixel_type) * width * height / 8;
                            out_buffer = eb.PvBuffer()
                            result, decompressed_buffer = decompression_filter.Execute(pvbuffer, out_buffer)
                            image = decompressed_buffer.GetImage()
                            if result.IsOK():
                                decompressed_size = decompressed_buffer.GetSize()
                                compression_ratio = decompressed_size / pvbuffer.GetAcquiredSize()
                                if calculated_size != decompressed_size:
                                    errors = errors + 1
                                print(f" Pleora compressed type.   Compression ratio: {'{0:.2f}'.format(compression_ratio)}  Errors: {errors}", end='')
                            else:
                                print(f" Could not decompress (Pleora compressed)", end='')
                                errors = errors + 1
                        else:
                            print(f" Could not read header (Pleora compressed)", end='')
                            errors = errors + 1
                    else:
                        print(f" Contents do not match payload type (Pleora compressed)", end='')
                        errors = errors + 1

                else:
                    print(" Payload type not supported by this sample", end='')

                if image:
                    print(f" W: {image.GetWidth()} H: {image.GetHeight()}", end='')
                    if opencv_is_available:
                        image_data = image.GetDataPointer()
                        if image.GetPixelType() == eb.PvPixelMono8:
                            display_image = True
                        if image.GetPixelType() == eb.PvPixelRGB8:
                            image_data = cv2.cvtColor(image_data, cv2.COLOR_RGB2BGR)
                            display_image = True

                        if display_image:
                            cv2.imshow("stream",image_data)
                        else:
                            if not warning_issued:
                                # 显示一条消息，说明视频仅显示 Mono8 / RGB8 图像
                                print(f" ")
                                print(f" Currently only Mono8 / RGB8 images are displayed", end='\r')
                                print(f"")
                                warning_issued = True

                        if cv2.waitKey(1) & 0xFF != 0xFF:
                            break

                print(f" {frame_rate_val:.1f} FPS  {bandwidth_val / 1000000.0:.1f} Mb/s     ", end='\r')
            else:
                # 非 OK 操作结果
                print(f"{doodle[ doodle_index ]} {operational_result.GetCodeString()}       ", end='\r')
            # 将 pvbuffer 释放回管道
            pipeline.ReleaseBuffer(pvbuffer)
        else:
            # 检索 pvbuffer 失败
            print(f"{doodle[ doodle_index ]} {result.GetCodeString()}      ", end='\r')

        doodle_index = (doodle_index + 1) % 6
        if kb.kbhit():
            kb.getch()
            break;

    kb.stop()
    if opencv_is_available:
        cv2.destroyAllWindows()

    # 告诉设备停止发送图像。
    print("\nSending AcquisitionStop command to the device")
    stop.Execute()

    # 禁用设备上的流
    print("Disable streaming on the controller.")
    device.StreamDisable()

    # 停止管道
    print("Stop pipeline")
    pipeline.Stop()


print("PvPipelineSample:")

connection_ID = psu.PvSelectDevice()
if connection_ID:
    device = connect_to_device(connection_ID)
    if device:
        stream = open_stream(connection_ID)
        if stream:
            configure_stream(device, stream)
            pipeline = create_pipeline(device, stream)
            if pipeline:
                if register_events:
                    event_sink = my_pipeline_event_sink()
                    pipeline.RegisterEventSink(event_sink)
                acquire_images(device, stream, pipeline)
            
            # 关闭流
            if register_events:
                pipeline.UnregisterEventSink(event_sink)
            print("Closing stream")
            stream.Close()
            eb.PvStream.Free(stream)

        # 断开设备连接
        print("Disconnecting device")
        device.Disconnect()
        eb.PvDevice.Free(device)

print("<press a key to exit>")
kb.start()
kb.getch()
kb.stop()
