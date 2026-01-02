"""
文件名称: EventSample.py
功能描述:
    该脚本演示了如何使用 `eb.PvDevice` 对象来处理来自 GigE Vision 或 USB3 Vision 设备的事件。
    它连接到设备，并注册一个 `EventHandler` 类作为事件接收器。
    `EventHandler` 类（定义在 `EventSample/EventHandler.py` 中）将处理特定的设备事件。

特别注意事项:
    1. 脚本依赖 `EventSample` 子目录下的 `EventHandler` 模块。
    2. 在断开连接之前，必须先注销事件接收器 (`UnregisterEventSink`)。
"""
#!/usr/bin/env python3
'''
*****************************************************************************
*
*   Copyright (c) 2023, Pleora Technologies Inc., All rights reserved.
*
*****************************************************************************

Shows how to use a PvDevice object to handle events from a GigE Vision or
USB3 Vision device.
'''

import sys
import os
import numpy as np
import eBUS as eb
import lib.PvSampleUtils as psu

# 将 EventSample 目录添加到系统路径，以便导入 EventHandler
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "EventSample"))
try:
    from EventHandler import EventHandler
except ImportError as e:
    print(f"Unable to import required modules: {e}")
    exit(1)

kb = psu.PvKb()

def connect_to_device(connection_ID):
    # 连接到 GigE Vision 或 USB3 Vision 设备
    print("Connecting to device.")
    result, device = eb.PvDevice.CreateAndConnect(connection_ID)
    if device == None:
        print("Unable to connect to device: {result.GetCodeString()} ({result.GetDescription()})")
    return device

print("EventSample:")

# 选择设备
connection_ID = psu.PvSelectDevice()
if connection_ID:
    device = connect_to_device(connection_ID)
    if device:

        event_handler = EventHandler()
        # 注册 EventHandler 类作为事件接收器。参见 EventHandler.py。
        device.RegisterEventSink( event_handler )

        print("<press a key to disconnect>")
        kb.start()
        kb.getch()
        kb.stop()

        # 注销事件接收器
        device.UnregisterEventSink( event_handler )

        # 断开设备连接
        print("Disconnecting device")
        device.Disconnect()
        eb.PvDevice.Free(device)

print("<press a key to exit>")
kb.start()
kb.getch()
kb.stop()
