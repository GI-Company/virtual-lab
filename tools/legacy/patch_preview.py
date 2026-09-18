import sys

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'r') as f:
    content = f.read()

target = """            // Create metadata packet
            val metadata = CameraFrameMetadata(
                schemaVersion = "1",
                deviceId = deviceId,
                cameraId = activeCameraId,"""

replacement = """            // Create metadata packet
            val metadata = CameraFrameMetadata(
                schemaVersion = "1",
                messageType = "CAMERA_PREVIEW_FRAME",
                deviceId = deviceId,
                cameraId = activeCameraId,"""

if target in content:
    content = content.replace(target, replacement)
    with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'w') as f:
        f.write(content)
    print("Success")
else:
    print("Target not found")
