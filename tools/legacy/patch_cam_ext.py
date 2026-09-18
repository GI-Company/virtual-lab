import re

with open('./app/src/main/java/com/example/camera/CameraControlExtensions.kt', 'r') as f:
    content = f.read()

content = content.replace("val hwLevel = get(CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL) ?: CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_LEGACY\n    val manualSensor = hwLevel == CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_FULL || hwLevel == CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_3",
"""val hwLevel = get(CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL) ?: CameraCharacteristics.INFO_SUPPORTED_HARDWARE_LEVEL_LEGACY
    val capabilities = get(CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES) ?: IntArray(0)
    val manualSensor = capabilities.contains(CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES_MANUAL_SENSOR)""")

content = content.replace("val capabilities = get(CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES) ?: IntArray(0)\n    val rawSupported = capabilities.contains(CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES_RAW)\n    val yuvSupported = capabilities.contains(CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES_YUV_REPROCESSING)",
"""val rawSupported = capabilities.contains(CameraCharacteristics.REQUEST_AVAILABLE_CAPABILITIES_RAW)
    val yuvSupported = streamMap?.getOutputSizes(android.graphics.ImageFormat.YUV_420_888)?.isNotEmpty() == true""")

with open('./app/src/main/java/com/example/camera/CameraControlExtensions.kt', 'w') as f:
    f.write(content)
