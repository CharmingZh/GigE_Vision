"""
文件名称: ConnectionRecovery.py
功能描述:
    该脚本演示了如何在连接断开（例如网线拔出）后自动恢复与设备的连接。
    它定义了一个应用程序类 `connection_recovery_app`，该类继承自 `eb.PvDeviceEventSink` 以处理设备事件。
    主要功能包括：
    1. 选择并连接设备。
    2. 打开流并配置管道进行图像采集。
    3. 在主循环中持续获取图像。
    4. 监听 `OnLinkDisconnected` 事件，当连接丢失时设置标志。
    5. 在主循环中检测到连接丢失后，自动清理资源并尝试重新连接。

特别注意事项:
    1. 建议设备使用静态 IP 或通过 MAC 地址（GUID）进行连接，以便在设备重启或网络恢复后能重新找到设备。
    2. 在 `OnLinkDisconnected` 回调中，不要直接断开设备连接，应设置标志位由主线程处理，以避免死锁或线程安全问题。
    3. 脚本依赖 `lib.PvSampleUtils`。
"""
#!/usr/bin/env python3

'''
*****************************************************************************

    Copyright (c) 2022, Pleora Technologies Inc., All rights reserved.

*****************************************************************************


'''

import time
import sys
import os
import eBUS as eb
import lib.PvSampleUtils as psu

# 初始化键盘监听
kb = psu.PvKb()

#
# 应用程序类
#

class connection_recovery_app(eb.PvDeviceEventSink):

    def __init__( self ):
        print(f"Time to init")
        self.__connectionID = ""
        self.__connection_lost = False
        self.__device = None
        self.__stream = None
        self.__pipeline = None
        # 初始化父类
        eb.PvDeviceEventSink.__init__(self)

    #
    # 主函数，运行应用程序
    #
    def run(self):
        # 选择设备
        if not self._select_device():
            return False

        # 进入采集循环，直到用户按键退出
        self._application_loop() 

        # 关闭流，断开连接等清理工作
        self._tear_down(True)
     
        return True

    #
    # 选择要操作的设备
    #
    def _select_device( self ):
        print(f"--> SelectDevice")

        # 调用工具函数选择设备，返回连接 ID
        self.__connectionID = psu.PvSelectDevice();
        if not self.__connectionID:
            print(f"No device selected.")
            return False

        #/ 重要提示: 
        #/
        #/ 这里我们假设设备在恢复连接时会保持相同的 IP 地址（通过 DHCP、静态 IP 或 LLA）。
        #/ 如果设备可能以不同的 IP 地址重新上线，应该使用设备的 MAC 地址作为连接 ID。
        #/ 虽然效率稍低，但允许在 IP 变更的情况下重新连接。
        #/
        #/ 对于 USB3 Vision 设备，这不适用，因为它们总是保持相同的设备 GUID。
        #/
        return True

    #
    # 连接设备
    #
    def _connect_device(self):
        print(f"--> ConnectDevice {self.__connectionID}")

        # 连接到选定的设备
        result, self.__device = eb.PvDevice.CreateAndConnect( self.__connectionID );
        if not result.IsOK():
            return False

        # 注册此类为 PvDevice 回调的事件接收器
        self.__device.RegisterEventSink(self);

        # 清除连接丢失标志，因为我们现在已连接到设备
        self.__connection_lost = False
        return True


    #
    # 打开流，管道，分配缓冲区
    #
    def _open_stream(self):
        print(f"--> OpenStream")

        # 基于选定的设备创建并打开流对象
        result, self.__stream = eb.PvStream.CreateAndOpen( self.__connectionID );
        if not result.IsOK():
            print(f"Unable to open the stream")
            return False;

        # 创建管道对象
        self.__pipeline = eb.PvPipeline( self.__stream );

        # 从设备读取 Payload Size (图像大小)
        size = self.__device.GetPayloadSize();

        # 初始化 PvPipeline 对象
        self.__pipeline.SetBufferSize(size);
        # 设置缓冲区数量为 16
        self.__pipeline.SetBufferCount( 16 );

        # 管道需要在我们指示设备发送图像之前“武装”或启动
        result = self.__pipeline.Start();
        if not result.IsOK():
            print(f"Unable to start pipeline");
            return False;

        # 仅针对 GigE Vision 设备，如果支持的话
        if isinstance(self.__device, eb.PvDeviceGEV):
            parameters = self.__stream.GetParameters()
            request_missing_packets_node = parameters.Get("RequestMissingPackets")
            if not request_missing_packets_node == None:
                if request_missing_packets_node.IsAvailable():
                    # 禁用请求丢失的数据包功能，以减少网络负载
                    request_missing_packets_node.SetValue( False ) 

        print(f"Connected to {self.__connectionID}")
        parameters = self.__device.GetParameters()
        
        return True

    #
    # 关闭流和管道
    #
    def _close_stream(self):
 
        print(f"--> CloseStream");

        if not self.__pipeline == None :
            if (  self.__pipeline.IsStarted() ):
                if not self.__pipeline.Stop().IsOK():
                    print(f"Unable to stop the pipeline.");

            del self.__pipeline
            self.__pipeline = None;

        if not self.__stream == None:
            if ( self.__stream.IsOpen()): 
                if not self.__stream.Close().IsOK():
                   print(f"Unable to stop the stream.")

            eb.PvStream.Free( self.__stream ) 
            self.__stream = None

    #
    # 开始图像采集
    # 如果设备从网络断开（例如拔线），OnLinkDisconnect 回调将执行，并尝试重新连接设备。
    #
    def _start_acquisition(self):
        print(f"--> StartAcquisition")
        print(f"")
        print(f"<press a key to exit>")

        # 设置流传输目标（仅限 GigE Vision 设备）
        if not (self.__device == None):
            if isinstance(self.__device, eb.PvDeviceGEV):
            # 清空数据包队列，确保没有上次断开连接遗留的数据
                if not self.__stream == None:
                    self.__stream.FlushPacketQueue()
                # 必须将设备 IP 目标设置为流的 IP 和端口
                result = self.__device.SetStreamDestination( self.__stream.GetLocalIPAddress(), self.__stream.GetLocalPort() )
                if not result.IsOK():
                    print(f"Setting stream destination failed")
                    return False 

        # 在发送 AcquisitionStart 命令之前启用流
        self.__device.StreamEnable()

        # 管道已经“武装”，我们只需告诉设备开始发送图像
        parameters = self.__device.GetParameters()
        acq_start_node = parameters.Get("AcquisitionStart") 
        result = acq_start_node.Execute() 
        if not result.IsOK():
            print(f"Unable to start acquisition")
            return False;

        return True;

    #
    # 停止采集
    #
    def _stop_acquisition(self):
        print(f"--> StopAcquisition")

        if not self.__device == None:
            # 告诉设备停止发送图像
            parameters = self.__device.GetParameters()
            acq_stop_node = parameters.Get("AcquisitionStop") 
            result = acq_stop_node.Execute();

            # 在发送 AcquisitionStop 命令后禁用流
            self.__device.StreamDisable()

            if isinstance(self.__device, eb.PvDeviceGEV):
                # 重置流传输目标（可选...）
                self.__device.ResetStreamDestination()

        return True

    #
    # 采集循环
    #
    def _application_loop(self):
        print(f"--> ApplicationLoop")

        doodle = "|\\-|-/"
        doodle_index = 0
        first_timeout = True

        image_count_val = 0
        frame_rate_val = 0.0
        bandwidth_val = 0.0

        kb = psu.PvKb()

        # 获取图像直到用户指示停止
        while not kb.kbhit():
            # 如果连接标志升起，拆除设备/流
            if ( self.__connection_lost and ( not self.__device == None ) ):
                # 设备丢失：无需停止采集（因为已经断了）
                self._tear_down( False )

            # 如果设备未连接，尝试重新连接
            if ( self.__device == None ):
                print(f"Attempt Reconnection")
                if ( self._connect_device() ):
                    print(f"Connected to device")

                    # 设备已连接，打开流
                    if self._open_stream():
                        if not self._start_acquisition():
                            self._tear_down(False)
                    else:
                        self._tear_down(False)

            # 如果仍然没有设备，无需继续循环
            if ( self.__device == None ):
                continue 

            if ( ( not self.__stream == None ) and  self.__stream.IsOpen() and 
                    ( not self.__pipeline == None ) and self.__pipeline.IsStarted() ):
                # 检索下一个缓冲区，超时 1000ms
                result, pvbuffer, operational_result = self.__pipeline.RetrieveNextBuffer(1000)
            
                if result.IsOK():
                    if operational_result.IsOK():
                        #
                        # 我们现在有一个有效的缓冲区。这是您通常处理缓冲区的地方。
                        #---------------------------------------------------------------------------------
                        #
                        result, image_count_val = self.__stream.GetParameters().GetIntegerValue("BlockCount")
                        result, frame_rate_val = self.__stream.GetParameters().GetFloatValue("AcquisitionRate")
                        result, bandwidth_val = self.__stream.GetParameters().GetFloatValue("Bandwidth")
               
                        # 如果缓冲区包含图像，显示宽度和高度
                        width = 0
                        height = 0
                        if ( pvbuffer.GetPayloadType() == eb.PvPayloadType.PvPayloadTypeImage.value ):
                            # 获取图像特定的缓冲区接口
                            image = pvbuffer.GetImage()

                            # 读取宽度，高度
                            width = image.GetWidth()
                            height = image.GetHeight()
                   
                        print(f"{doodle[ doodle_index ]}", end=" ") 
                        print(f" BlockID: {pvbuffer.GetBlockID():016d}   W: {width}  H: {height}", end=" ")
                        print(f" {frame_rate_val:.1f} FPS {bandwidth_val / 1000000.0:.1f} Mb/s \r", end=" ")

                        first_timeout = True 

                    # 我们有一个图像 - 做一些处理 (...) 并且非常重要：
                    # 将缓冲区释放回管道
                    self.__pipeline.ReleaseBuffer(pvbuffer) 
                else:
                    # 超时
                    if first_timeout:
                        print(f"") 
                        first_timeout = False 

                    print(f"Image timeout {doodle[doodle_index]} ")

                doodle_index = (doodle_index + 1) % 6 
            else:
                # 没有流/管道，必须处于恢复状态。稍等片刻...
                time.sleep(0.1) 
            
        print(f" ")

    #
    #  断开设备连接
    #
    def _disconnect_device(self):
        print(f"--> DisconnectDevice")

        if not self.__device == None:
            if self.__device.IsConnected():
                # 注销事件接收器（回调）
                self.__device.UnregisterEventSink( self )

            eb.PvDevice.Free(self.__device)
            self.__device = None

    #
    # 拆除：关闭，断开连接等
    #
    def _tear_down(self, stop_acquisition):
        print(f"--> TearDown")

        if ( stop_acquisition ):
            self._stop_acquisition()

        self._close_stream()
        self._disconnect_device()
        return eb.PV_OK

    # 
    # PvDeviceEventSink 回调
    # 
    # 设备刚刚断开连接的通知
    # 
    def OnLinkDisconnected( self, aDevice ):
        print(f"=====> PvDeviceEventSink::OnLinkDisconnected callback")

        # 仅设置标志指示我们丢失了设备。主循环将拆除设备/流并尝试重新连接。
        self.__connection_lost = True

        # 重要提示:
        # 绝不能从此回调中显式断开 PvDevice。
        # 这里我们只是升起一个标志，表示我们丢失了设备，让应用程序的主循环
        # （从主应用程序线程）执行断开连接。
        # 

#
# Main function
#

# Receives images using a PvPipeline, full recovery management.
print(f"***********************************************************") 
print(f"ConnectionRecovery sample- image acquisition from a device.")
print(f"*---------------------------------------------------------*")
print(f"* It is recommended to use a persistent, fixed IP address *")
print(f"* or GUID on a device when relying on automatic recovery. *")
print(f"***********************************************************")
print(f"<press a key to terminate the application>")

print(f"Starting")
lapplication = connection_recovery_app()
lRetVal = lapplication.run()
print(f"")

print("<press a key to exit>")
kb.start()
kb.getch()
kb.stop()
