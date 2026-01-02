"""
文件名称: DeviceSerialPort.py
功能描述:
    该脚本演示了如何使用 `PvDeviceSerialPort` 类通过 Pleora GigE Vision 或 USB3 Vision 设备进行串行通信。
    它连接到设备，配置串行端口（UART0 或 BULK0），并执行回环测试：
    1. 将数据写入串行端口。
    2. 从串行端口读取数据。
    3. 验证读取的数据是否与写入的数据一致。

特别注意事项:
    1. 脚本默认配置为回环模式 (`Loopback` = True)，因此不需要外部硬件连接即可测试。
    2. 支持 `UART0` 和 `BULK0` 两种端口模式，通过 `PORT` 变量配置。
    3. 测试数据量会随着迭代次数指数级增长。
"""
#!/usr/bin/env python3

'''
*****************************************************************************

    Copyright (c) 2022, Pleora Technologies Inc., All rights reserved.

*****************************************************************************


 This sample shows how to use the PvDeviceSerialPort class to communicate with a Pleora GigE Vision or USB3 Vision device.
'''

import sys
import random
import eBUS as eb
import numpy as np
import lib.PvSampleUtils as psu


PORT     = "BULK0"
SPEED    = "Baud9600"
STOPBITS = "One"
PARITY   = "None"

TEST_COUNT = 16

#
# 演示如何使用 PvDeviceSerialPort 向视频接口写入数据并连续读回
# （视频接口串口设置为回环模式）。
#
def TestSerialCommunications():
    connection_ID = psu.PvSelectDevice()
    if not connection_ID:
        print(f"No device selected." ) 
        return False 

    # 连接到 GEV 或 U3V 设备
    print(f"Connecting to device {connection_ID}")
    result, device = eb.PvDevice.CreateAndConnect(connection_ID) 
    if not result.IsOK():
        print(f"Unable to connect to device")
        return False;

    # 创建 PvDevice 适配器
    device_adapter = eb.PvDeviceAdapter( device );

    # 获取控制流所需的设备参数
    params = device.GetParameters();

    # 配置串口 - 这是直接在设备 GenICam 接口上完成的，而不是在串口对象上！
    if ( PORT == "UART0"):
        params.SetEnumValue( "Uart0BaudRate", SPEED );
        params.SetEnumValue( "Uart0NumOfStopBits", STOPBITS );
        params.SetEnumValue( "Uart0Parity", PARITY );

        # 为了在没有连接串行硬件的情况下进行此测试，我们启用端口回环
        params.SetBooleanValue( "Uart0Loopback", True );

    if (PORT == "BULK0"):
        params.SetEnumValue( "BulkSelector", "Bulk0" );
        params.SetEnumValue( "BulkMode", "UART" );
        params.SetEnumValue( "BulkBaudRate", SPEED );
        params.SetEnumValue( "BulkNumOfStopBits", STOPBITS );
        params.SetEnumValue( "BulkParity", PARITY );

        # 为了在没有连接串行硬件的情况下进行此测试，我们启用端口回环
        params.SetBooleanValue( "BulkLoopback", True );

    #  打开串口
    if (PORT == "UART0"):
        port = eb.PvDeviceSerialPort() 
        result = eb.PvDeviceSerialPort.Open(port, device_adapter, eb.PvDeviceSerialUart0 );

    if (PORT == "BULK0"):
        port = eb.PvDeviceSerialPort() 
        result = port.Open( device_adapter, eb.PvDeviceSerialBulk0 );

    if not result.IsOK():
        print(f"Unable to open serial port on device: {result.GetCodeString()} {result.GetDescription()}" )
        return False;

    print(f"Serial port opened");

    size = 1;
#   确保 PvDeviceSerialPort 接收队列足够大以缓冲所有字节
#   注意，在下面的测试中，每次迭代 lSize 都会加倍，所以 lSize << TEST_COUNT 是大小（2x 以提供额外空间）
    port.SetRxBufferSize( ( size << TEST_COUNT ) * 2);

    
    for count in range(0, TEST_COUNT):
        in_buffer = np.zeros(size, dtype= np.uint8)
        out_buffer = np.zeros(size, dtype= np.uint8)

        # 用随机数据填充输入缓冲区
        for i in range(0, size):
            j = random.randrange(256)
            in_buffer[i] = j

        # 在串口上发送缓冲区内容
        bytes_written = 0;
        result, bytes_written = port.Write( in_buffer )
        print(f"Sent {bytes_written} bytes through the serial port")
        if not result.IsOK():
            # 无法通过串口发送数据！
            print(f"Error sending data over the serial port: {result.GetCodeString()}  {result.GetDescription()} ");
            break 
 

        # 等待直到我们收到所有字节或超时。Read 方法仅在函数调用时没有可用数据时才会超时，
        # 否则它返回所有当前可用的数据。如果尚未收到所有预期数据，我们可能需要多次调用 Read
        # 来检索所有数据。
        
        # 您自己驱动串行协议的代码应该检查消息是否完整，
        # 无论是基于某种 EOF 还是长度。您应该不断读出数据，直到
        # 获得您正在等待的内容或达到某个超时。
        
        total_bytes_read = 0;

        while (total_bytes_read < size):
            bytes_read = 0
            
            result, out_buffer[ total_bytes_read:size ], bytes_read = port.Read( size - total_bytes_read, 500 );
            left_to_read = size - total_bytes_read
            # 真正的读取代码结束
            if ( result.GetCode() == eb.PV_TIMEOUT ):
                print(f"Timeout")
                break;

            # 增加读取头
            total_bytes_read += bytes_read 

        # 验证答案
        if not total_bytes_read == bytes_written:
            # 没有收到所有预期的字节
            print(f"Only received {total_bytes_read} out of {bytes_written} bytes")
        else:
            # 比较输入和输出缓冲区
            error_count = 0;
            for i in range(0, bytes_written ):
                if not in_buffer[ i ] == out_buffer[ i ]:
                    error_count = error_count + 1;

            # 显示错误计数
            print(f"Error count: {error_count}")

        del in_buffer; 
        
        del out_buffer; 

        # 增加测试用例大小
        size *= 2;

        print(f"")


    # 关闭串口
    port.Close();
    print(f"Serial port closed")

    # 删除设备适配器（在释放 PvDevice 之前！）
    del device_adapter;

    # 释放设备。使用 PvDevice::Free，因为设备是使用 PvDevice::CreateAndConnect 分配的。
    print(f"Disconnecting and freeing device")
    eb.PvDevice.Free(device );

    return True;
 

#
# 入口代码
#

#   PvDeviceSerialPort 用于通过 Pleora GigE Vision 或 USB3 Vision 设备执行串行通信

print(f"DeviceSerialPort Sample");
TestSerialCommunications();
print(f"")

print(f"<press a key to exit>")
kb = psu.PvKb()
kb.start()
kb.getch()
kb.stop()


