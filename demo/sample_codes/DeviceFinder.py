"""
文件名称: DeviceFinder.py
功能描述:
    该脚本演示了如何使用 `eb.PvSystem` 类来查找和枚举网络上的 GigE Vision 设备或连接的 USB3 Vision 设备。
    它会列出所有找到的接口（网卡或 USB 控制器）以及连接到这些接口的设备信息（如 MAC 地址、IP 地址、序列号等）。
    此外，它还演示了如何连接到找到的第一个设备，并注册一个事件接收器来监听连接断开事件。

特别注意事项:
    1. 脚本会尝试连接找到的第一个设备，然后立即断开连接。
    2. 使用 `logging` 模块输出调试信息。
    3. 定义了一个 `my_event_sink` 类来处理设备事件。
"""
#!/usr/bin/env python3

import eBUS as eb
import logging
import sys
import lib.PvSampleUtils as psu

kb = psu.PvKb()

# 示例：在设备上使用事件接收器。
class my_event_sink(eb.PvDeviceEventSink):
    def __init__(self, logger):
        super().__init__()
        self.logger = logger

    # 当连接断开时调用
    def OnLinkDisconnected(self, device):
        uniqueID = device.GetUniqueID()
        self.logger.info("Got a disconnect from %s", uniqueID)

    # 当读取到命令链接数据时调用（通常用于调试）
    def OnCmdLinkRead(self, args):
        (buffer, address) = args
        self.logger.debug("OnCmdLinkRead buffer: %s  address: %d", buffer, address)

print("DeviceFinder sample")

# 创建 PvSystem 对象，它是查找设备的入口点
pvsystem = eb.PvSystem()

# 开始查找设备（设置超时时间等，这里使用默认值）
result = pvsystem.Find()

if not result.IsOK():
    print(f"Unable to find devices: {result.GetCodeString()}")
    exit(1)

# 获取找到的接口数量
interface_count = pvsystem.GetInterfaceCount()

device_info = None

# 遍历所有接口
for x in range(interface_count):
    print(f"")
    print(f"Interface {x}")
    interface = pvsystem.GetInterface(x)

    # 如果是网络适配器
    if isinstance(interface, eb.PvNetworkAdapter):
        print(f"  MAC Address: {interface.GetMACAddress()}")
        for z in range(interface.GetIPAddressCount()):
            print(f"  IP Address {z}: {interface.GetIPAddress(z)}")
            print(f"  Subnet Mask {z}: {interface.GetSubnetMask(z)}")

    # 如果是 USB 主机控制器
    elif isinstance(interface, eb.PvUSBHostController):
        print(f"  Name: {interface.GetName()}")

    # 遍历接口上的所有设备
    for y in range(interface.GetDeviceCount()):
        device_info = interface.GetDeviceInfo(y)
        print(f"")
        print(f"  Device {y}")
        print(f"    Display ID: {device_info.GetDisplayID()}")
        print(f"    Serial Number: {device_info.GetSerialNumber()}")

        # 根据设备类型打印特定信息
        if isinstance(device_info, eb.PvDeviceInfoGEV) \
                or isinstance(device_info, eb.PvDeviceInfoPleoraProtocol):
            print(f"    MAC Address: {device_info.GetMACAddress()}")
            print(f"    IP Address: {device_info.GetIPAddress()}")
        elif isinstance(device_info, eb.PvDeviceInfoU3V):
            print(f"    GUID: {device_info.GetDeviceGUID()}")
            print(f"    Speed: {device_info.GetSpeed()}")
        elif isinstance(device_info, eb.PvDeviceInfoUSB):
            print(f"    Unknown USB device?")

logger = logging.getLogger()

# 更改日志级别以查看不同的日志（INFO 或 DEBUG）
logging.basicConfig(stream=sys.stdout, level=logging.ERROR)

logger.info("Creating event sink")
event_sink = my_event_sink(logger)

# 如果找到了设备，尝试连接第一个找到的设备
if device_info:
    print(f"Connecting to {device_info.GetDisplayID()}")
    result, device = eb.PvDevice.CreateAndConnect(device_info)
    if result.IsOK():
        print(f"Successfully connected to {device_info.GetDisplayID()}")
        # 注册事件接收器
        device.RegisterEventSink(event_sink)
        print(f"Disconnecting the device {device_info.GetDisplayID()}")
        # 释放设备
        eb.PvDevice.Free(device)
    else:
        print(
            f"Unable to connect to {device_info.GetDisplayID()}: {result.GetCodeString()}")
else:
    print("No device found.")

print("<press a key to exit>")
kb.start()
kb.getch()
kb.stop()
