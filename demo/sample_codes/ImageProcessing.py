"""
文件名称: ImageProcessing.py
功能描述:
    该脚本演示了如何使用 `PvStream` 对象从 GigE Vision 或 USB3 Vision 设备采集图像，
    并使用 `process_pv_buffer` 函数对图像缓冲区执行 OpenCV 处理（如绘制文本和圆圈）。
    它还展示了如何将采集到的图像显示在窗口中。

特别注意事项:
    1. 脚本依赖 `opencv-python` (cv2) 进行图像处理和显示。如果未安装，将无法显示图像。
    2. 仅支持 Mono8 和 RGB8 格式的图像进行 OpenCV 处理和显示。
    3. 演示了手动管理 `PvBuffer` 队列的过程（分配、入队、检索、释放）。
"""
#!/usr/bin/env python3
'''
*****************************************************************************
*
*   Copyright (c) 2023, Pleora Technologies Inc., All rights reserved.
*
*****************************************************************************

Shows how to use a PvStream object to acquire images from a GigE Vision or
USB3 Vision device, and then use a ProcessPV buffer routine to perform CV2 
actions upon the buffer.
'''

import numpy as np
import eBUS as eb
import lib.PvSampleUtils as psu

BUFFER_COUNT = 16

kb = psu.PvKb()
opencv_is_available=True
try:
    # 检测 OpenCV 是否可用
    import cv2
    opencv_version=cv2.__version__
except:
    opencv_is_available=False
    print("Warning: This sample requires python3-opencv to display a window")

def connect_to_device(connection_ID):
    # 连接到 GigE Vision 或 USB3 Vision 设备
    print("Connecting to device.")
    result, device = eb.PvDevice.CreateAndConnect(connection_ID)
    if device == None:
        print(f"Unable to connect to device: {result.GetCodeString()} ({result.GetDescription()})")
    return device

def open_stream(connection_ID):
    # 打开到 GigE Vision 或 USB3 Vision 设备的流
    print("Opening stream from device.")
    result, stream = eb.PvStream.CreateAndOpen(connection_ID)
    if stream == None:
        print(f"Unable to stream from device. {result.GetCodeString()} ({result.GetDescription()})")
    return stream

def configure_stream(device, stream):
    # 如果是 GigE Vision 设备，配置 GigE Vision 特定的流参数
    if isinstance(device, eb.PvDeviceGEV):
        # 协商数据包大小
        device.NegotiatePacketSize()
        # 配置设备流传输目标
        device.SetStreamDestination(stream.GetLocalIPAddress(), stream.GetLocalPort())

def configure_stream_buffers(device, stream):
    buffer_list = []
    # 从设备读取 Payload Size (图像大小)
    size = device.GetPayloadSize()

    # 使用 BUFFER_COUNT 或最大缓冲区数量，取较小值
    buffer_count = stream.GetQueuedBufferMaximum()
    if buffer_count > BUFFER_COUNT:
        buffer_count = BUFFER_COUNT

    # 分配缓冲区
    for i in range(buffer_count):
        # 创建新的 pvbuffer 对象
        pvbuffer = eb.PvBuffer()
        # 让新的 pvbuffer 对象分配 payload 内存
        pvbuffer.Alloc(size)
        # 添加到外部列表 - 用于最终释放缓冲区
        buffer_list.append(pvbuffer)
    
    # 将所有缓冲区入队到流中
    for pvbuffer in buffer_list:
        stream.QueueBuffer(pvbuffer)
    print(f"Created {buffer_count} buffers")
    return buffer_list


def process_pv_buffer( pvbuffer ):
    """
    使用此方法通过您自己的算法处理缓冲区。
    """
    print_string_value = "Image Processing"

    image = pvbuffer.GetImage()
    pixel_type = image.GetPixelType()

    # 验证我们是否可以处理此格式，否则继续。
    if (pixel_type != eb.PvPixelMono8) and (pixel_type != eb.PvPixelRGB8):
        return pvbuffer

    # 检索 Numpy 数组
    image_data = image.GetDataPointer()

    # 这里是一个使用 opencv 在图像中放置一些文本和一个圆圈的示例。
    cv2.putText(image_data, print_string_value,
                (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, 0, 4)

    # 将圆圈放置在图像中间
    circle_centre_width_pos = image.GetWidth() // 2
    circle_centre_height_pos = image.GetHeight() // 2
    cv2.circle(image_data, ( circle_centre_width_pos, circle_centre_height_pos ), 
            50, 0, 4 )
    return 



def acquire_images(device, stream):
    # 获取控制流所需的设备参数
    device_params = device.GetParameters()

    # 映射 GenICam AcquisitionStart 和 AcquisitionStop 命令
    start = device_params.Get("AcquisitionStart")
    stop = device_params.Get("AcquisitionStop")

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

    # 获取图像直到用户指示停止。
    print("\n<press a key to stop streaming>")
    kb.start()
    while not kb.is_stopping():
        # 检索下一个 pvbuffer，超时 1000ms
        result, pvbuffer, operational_result = stream.RetrieveBuffer(1000)
        if result.IsOK():
            if operational_result.IsOK():
                #
                # 我们现在有一个有效的 pvbuffer。
                # 这是您通常处理 pvbuffer 的地方。
                if opencv_is_available:
                    process_pv_buffer(pvbuffer)
                # ...

                result, frame_rate_val = frame_rate.GetValue()
                result, bandwidth_val = bandwidth.GetValue()

                print(f"{doodle[doodle_index]} BlockID: {pvbuffer.GetBlockID():016d}", end='')

                payload_type = pvbuffer.GetPayloadType()
                if payload_type == eb.PvPayloadTypeImage:
                    image = pvbuffer.GetImage()
                    image_data = image.GetDataPointer()
                    print(f" W: {image.GetWidth()} H: {image.GetHeight()} ", end='')
                    
                    if opencv_is_available:
                        if image.GetPixelType() == eb.PvPixelMono8:
                            display_image = True
                        if image.GetPixelType() == eb.PvPixelRGB8:
                            # OpenCV 使用 BGR，所以如果源是 RGB，需要转换
                            image_data = cv2.cvtColor(image_data, cv2.COLOR_RGB2BGR)
                            display_image = True

                        if display_image:
                            cv2.imshow("stream", image_data)
                        else:
                            if not warning_issued:
                                # 显示一条消息，说明视频仅显示 Mono8 / RGB8 图像
                                print(f" ")
                                print(f" Currently only Mono8 / RGB8 images are displayed", end='\r')
                                print(f"")
                                warning_issued = True

                        if cv2.waitKey(1) & 0xFF != 0xFF:
                            break

                elif payload_type == eb.PvPayloadTypeChunkData:
                    print(f" Chunk Data payload type with {pvbuffer.GetChunkCount()} chunks", end='')

                elif payload_type == eb.PvPayloadTypeRawData:
                    print(f" Raw Data with {pvbuffer.GetRawData().GetPayloadLength()} bytes", end='')

                elif payload_type == eb.PvPayloadTypeMultiPart:
                    print(f" Multi Part with {pvbuffer.GetMultiPartContainer().GetPartCount()} parts", end='')

                else:
                    print(" Payload type not supported by this sample", end='')

                print(f" {frame_rate_val:.1f} FPS  {bandwidth_val / 1000000.0:.1f} Mb/s     ", end='\r')
            else:
                # 非 OK 操作结果
                print(f"{doodle[ doodle_index ]} {operational_result.GetCodeString()}       ", end='\r')
            # 将 pvbuffer 重新入队到流对象中
            stream.QueueBuffer(pvbuffer)

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

    # 中止流中的所有缓冲区并出队
    print("Aborting buffers still in stream")
    stream.AbortQueuedBuffers()
    while stream.GetQueuedBufferCount() > 0:
        result, pvbuffer, lOperationalResult = stream.RetrieveBuffer()

print("ImageProcessing:")

connection_ID = psu.PvSelectDevice()
if connection_ID:
    device = connect_to_device(connection_ID)
    if device:
        stream = open_stream(connection_ID)
        if stream:
            configure_stream(device, stream)
            buffer_list = configure_stream_buffers(device, stream)
            acquire_images(device, stream)
            buffer_list.clear()
            
            # 关闭流
            print("Closing stream")
            stream.Close()
            eb.PvStream.Free(stream);    

        # 断开设备连接
        print("Disconnecting device")
        device.Disconnect()
        eb.PvDevice.Free(device)

print("<press a key to exit>")
kb.start()
kb.getch()
kb.stop()
