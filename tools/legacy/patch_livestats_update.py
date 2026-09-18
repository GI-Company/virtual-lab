import sys

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'r') as f:
    content = f.read()

target = """            _liveStats.value = LiveCameraStats(
                cameraId = activeCameraId,
                cameraLabel = activeCameraLabel,
                resolution = "${image.width}x${image.height}",
                observedFps = Math.round(observedFps * 10.0) / 10.0,
                totalFrames = totalFrames,
                droppedFrames = droppedFrames,
                exposureTimeNs = expTime,
                iso = iso,
                focalLengthMm = focalLen,
                focusDistance = focusDist,
                timestampNs = devTimestamp,
                bitrateKbps = Math.round(bitrateKbps * 10.0) / 10.0,
                thermalStatus = thermalMonitor.thermalStatus.value
            )"""

replacement = """            _liveStats.value = _liveStats.value.copy(
                resolution = "${image.width}x${image.height}",
                observedFps = Math.round(observedFps * 10.0) / 10.0,
                totalFrames = totalFrames,
                droppedFrames = droppedFrames,
                exposureTimeNs = expTime,
                iso = iso,
                focalLengthMm = focalLen,
                focusDistance = focusDist,
                timestampNs = devTimestamp,
                bitrateKbps = Math.round(bitrateKbps * 10.0) / 10.0,
                thermalStatus = thermalMonitor.thermalStatus.value
            )"""

if target in content:
    content = content.replace(target, replacement)
    with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'w') as f:
        f.write(content)
    print("Success")
else:
    print("Target not found")
