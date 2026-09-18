import sys

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'r') as f:
    content = f.read()

target = """            _liveStats.value = LiveCameraStats(
                cameraId = camera.id,
                cameraLabel = camera.friendlyName,
                resolution = "${previewSize.width}x${previewSize.height}",
                thermalStatus = thermalMonitor.thermalStatus.value
            )"""

replacement = """            val fpsRanges = chars.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES)
            val targetRange = fpsRanges?.firstOrNull { it.lower in 10..15 && it.upper in 15..30 }
                                ?: fpsRanges?.firstOrNull { it.upper <= 30 }
            val rangeStr = targetRange?.let { "${it.lower}-${it.upper}" } ?: "UNKNOWN"

            _liveStats.value = LiveCameraStats(
                cameraId = camera.id,
                cameraLabel = camera.friendlyName,
                logicalCameraId = camera.parentLogicalCameraId,
                physicalCameraId = if (camera.parentLogicalCameraId != null) camera.id else null,
                lensFacing = camera.lensFacing.name,
                hardwareLevel = camera.hardwareLevel,
                hasRaw = camera.hasRaw,
                configuredFpsRange = rangeStr,
                resolution = "${previewSize.width}x${previewSize.height}",
                thermalStatus = thermalMonitor.thermalStatus.value
            )"""

if target in content:
    content = content.replace(target, replacement)
    with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'w') as f:
        f.write(content)
    print("Success")
else:
    print("Target not found")
