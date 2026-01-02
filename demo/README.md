# eBUS SDK Python 示例代码说明

本目录包含使用 Pleora eBUS SDK 的 Python 示例代码。这些示例展示了如何连接设备、配置流、采集图像以及处理不同类型的 Payload。

## 目录结构

- `read_from_raw.py`: 读取 `.bin` 原始数据文件并转换为图像或视频。
- `test.py`: 演示多线程图像采集和保存。
- `sample_codes/`: 包含官方示例的修改版本，添加了中文注释。

## 示例代码详解 (sample_codes)

以下是 `sample_codes` 目录下各个文件的功能说明：

### 基础连接与配置
1.  **DeviceFinder.py**
    *   **功能**: 搜索并列出网络上的 GigE Vision 设备和 USB 总线上的 USB3 Vision 设备。
    *   **用途**: 确认设备是否被系统识别，获取连接 ID。

2.  **ConnectionRecovery.py**
    *   **功能**: 演示如何在连接断开（如网线拔出）后自动重新连接设备。
    *   **用途**: 开发健壮的工业应用，确保系统在网络波动后能自动恢复。

3.  **GenICamParameters.py**
    *   **功能**: 演示如何通过 GenICam 接口读取和设置设备参数（如 ExposureTime, Gain 等）。
    *   **用途**: 学习如何通过代码控制相机的所有功能。

### 图像采集 (核心)
4.  **PvPipelineSample.py**
    *   **功能**: 使用 `PvPipeline` 类进行图像采集。
    *   **特点**: `PvPipeline` 自动管理缓冲区队列，是最常用的采集方式。支持多种 Payload 类型（Image, ChunkData, MultiPart 等）。

5.  **PvStreamSample.py**
    *   **功能**: 使用 `PvStream` 类进行图像采集。
    *   **特点**: 需要手动管理缓冲区的分配、入队和出队。适合需要对内存管理进行精细控制的高级用户。

6.  **ImageProcessing.py**
    *   **功能**: 采集图像并使用 OpenCV 进行处理（如显示、格式转换）。
    *   **用途**: 演示 eBUS SDK 与 OpenCV 的集成。

### 高级功能
7.  **EventSample.py**
    *   **功能**: 接收和处理设备事件（如参数更改、触发信号等）。
    *   **用途**: 监控设备状态变化。

8.  **DeviceSerialPort.py**
    *   **功能**: 通过相机的串口（UART）与外部设备通信。
    *   **用途**: 控制连接到相机的光源、镜头或其他串口设备。

9.  **MultiSource.py**
    *   **功能**: 从多源设备（如双传感器相机或采集卡）并行采集图像。
    *   **用途**: 处理多通道同步采集。

10. **ReceiveMultiPart.py**
    *   **功能**: 接收 Multi-Part Payload（通常用于 3D 相机，包含深度图、置信度图等）。
    *   **用途**: 处理复杂的 3D 数据流。

## 使用方法

1.  确保已安装 eBUS SDK 和 Python 绑定。
2.  安装依赖库：
    ```bash
    pip install opencv-python numpy
    ```
3.  运行示例：
    ```bash
    python sample_codes/PvPipelineSample.py
    ```

## 注意事项

*   所有示例均已添加中文注释，详细解释了关键代码段的作用。
*   部分示例依赖 OpenCV (`cv2`) 进行图像显示。如果未安装 OpenCV，图像显示功能将被禁用，但采集功能仍然工作。
