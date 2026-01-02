"""
文件名称: GenICamParameters.py
功能描述:
    该脚本演示了如何以编程方式控制和访问 GenICam 参数。
    它展示了如何：
    1. 获取并显示主机的通信链路参数。
    2. 连接设备并显示设备的 GenICam 参数（如 Width, Height 等）。
    3. 演示如何读取、修改和恢复参数值（以 Width 为例）。
    4. 打开流并显示流控制器的参数。

特别注意事项:
    1. 脚本中包含一个 `dump_gen_parameter_array` 函数，用于遍历并打印参数数组中的所有可见参数。
    2. 演示了如何处理不同类型的 GenICam 参数（Integer, Enum, Boolean, String, Float, Command）。
    3. 在修改参数（如 Width）时，需要注意设备是否处于只读模式。
"""
#!/usr/bin/env python3

'''
*****************************************************************************

    Copyright (c) 2022, Pleora Technologies Inc., All rights reserved.

*****************************************************************************


This sample shows you how to control features programmatically.
'''

import sys
import os
import time
import eBUS as eb
import lib.PvSampleUtils as psu

#  让用户选择一个设备并将 PvDevice 对象连接到用户的选择。
#  注意：用户负责在不再需要时删除 PvDevice 对象。
def connect(connection_ID):
    # 连接到 GigE Vision 或 USB3 Vision 设备
    print(f"Connecting device")

    result, device = eb.PvDevice.CreateAndConnect(connection_ID) 
    if not result.IsOK():
        print(f"Unable to connect to device") 
        device.Free()
        return None

    return device 
 
#
# 转储 PvGenParameterArray 的全部内容。
#
def dump_gen_parameter_array( param_array ):

    # 获取数组大小
    parameter_array_count = param_array.GetCount();
    print(f"")
    print(f"Array has {parameter_array_count} parameters")

    # 遍历数组并打印可用参数。
    for x in range(parameter_array_count):
        # 获取一个参数
        gen_parameter = param_array.Get(x)

        # 不显示不可见参数 - 显示直到 Guru 级别的所有参数。
        result, lVisible = gen_parameter.IsVisible(eb.PvGenVisibilityGuru)
        if not lVisible:
            continue

        # 获取并打印参数名称。
        result, category = gen_parameter.GetCategory();
        result, gen_parameter_name = gen_parameter.GetName()
        print(f"{category}:{gen_parameter_name},", end=' ')

        # 参数可用吗？
        result, lAvailable = gen_parameter.IsAvailable()
        if not lAvailable:
            not_available = "{Not Available}"
            print(f"{not_available}");
            continue;

        # 参数可读吗？
        result, lReadable = gen_parameter.IsReadable()
        if not lReadable:
            not_readable = "{Not Readable}"
            print(f"{not_readable}")
            continue;
        
        #/ 获取参数类型
        result, gen_type = gen_parameter.GetType();
        if eb.PvGenTypeInteger == gen_type:
            result, value = gen_parameter.GetValue()
            print(f"Integer: {value}")
        elif eb.PvGenTypeEnum == gen_type:
            result, value = gen_parameter.GetValueString()
            print(f"Enum: {value}")
        elif eb.PvGenTypeBoolean == gen_type:
            result, value = gen_parameter.GetValue()
            if value:
                print(f"Boolean: TRUE")
            else:
                print(f"Boolean: FALSE")
        elif eb.PvGenTypeString == gen_type:
            result, value = gen_parameter.GetValue()
            print(f"String: {value}")
        elif eb.PvGenTypeCommand == gen_type:
            print(f"Command")
        elif eb.PvGenTypeFloat == gen_type:
            result, value = gen_parameter.GetValue()
            print(f"Float: {value}")


# 获取主机的通信相关设置。

def get_host_communication_related_settings( connection_ID ):
    # 通信链路可以在连接设备之前配置。
    # 无需连接到设备。
    print(f"Using non-connected PvDevice")
    device = eb.PvDeviceGEV()

    # 获取通信链路参数数组
    print(f"Retrieving communication link parameters array")
    comLink = device.GetCommunicationParameters();

    # 转储通信链路参数数组内容
    print(f"Dumping communication link parameters array content");
    dump_gen_parameter_array(comLink);

    device.Disconnect();

    return True;

#/
#/ 获取设备的设置
#/

def get_device_settings(connection_ID):
    # 连接到选定的设备。
    device = connect(connection_ID) 
    if device == None:
        return 
    
    # 获取设备的参数数组。它是根据设备本身提供的 GenICam XML 文件构建的。
    print(f"Retrieving device's parameters array")
    parameters = device.GetParameters()

    # 转储设备的参数数组内容。
    print(f"Dumping device's parameters array content")
    dump_gen_parameter_array(parameters)

    # 获取 Width 参数 - 强制性的 GigE Vision 参数，它应该存在。
    width_parameter = parameters.Get( "Width" );
    if ( width_parameter == None ):
        print(f"Unable to get the width parameter.")

    # 读取当前 Width 值。
    result, original_width = width_parameter.GetValue()
    if original_width == None:
        print(f"Error retrieving width from device")

    # 读取最大值。
    result, width_max = width_parameter.GetMax()
    if width_max == None:
        print(f"Error retrieving width max from device")   
        return

    # 更改 Width 值。
    result = width_parameter.SetValue(width_max)
    if not result.IsOK():
       print(f"Error changing width on device - the device is on Read Only Mode, please change to Exclusive to change value")

    # 将 Width 重置为原始值。
    result = width_parameter.SetValue(original_width)
    if not result.IsOK():
       print(f"1 Error changing width on device");   

    # 断开设备连接。
    eb.PvDevice.Free(device)
    return


#
# 获取图像流控制器设置。
#
def get_image_stream_controller_settings(connection_ID):

    # 创建流对象
    print(f"Opening stream")

    result, stream = eb.PvStream.CreateAndOpen(connection_ID) 
    if not result.IsOK():
        print(f"Error creating and opening stream")
        eb.PvStream.Free(stream );

    # 获取流参数。这些用于配置/控制一些流相关的参数和时序，并提供对此流统计信息的访问。
    print(f"Retrieving stream's parameters array")
    parameters = stream.GetParameters();

    # 转储流的参数数组内容。
    print(f"Dumping stream's parameters array content")
    dump_gen_parameter_array(parameters)

    # 关闭并释放 PvStream
    eb.PvStream.Free(stream)


#
# 主函数。
#
print(f"Device selection")
# connection_ID = psu.PvSelectDevice()
connection_ID = "169.254.101.209"
if connection_ID:
    print(f"GenICamParameters sample")
    print(f"")
    print(f"1. Communication link parameters display")
    get_host_communication_related_settings(connection_ID) 
    print(f"")

    # 设备参数显示。
    print(f"2. Device parameters display")
    print(f"")
    get_device_settings(connection_ID);

    #cout << endl;

    # 图像流参数显示。
    print(f"3. Image stream parameters display") 
    print(f"")
    get_image_stream_controller_settings(connection_ID) 

print(f"<press a key to exit>")

kb = psu.PvKb()
kb.start()
kb.getch()
kb.stop()


