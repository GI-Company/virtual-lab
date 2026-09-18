import sys

with open('./app/src/main/java/com/example/camera/CameraModels.kt', 'r') as f:
    content = f.read()

target = """data class LiveCameraStats(
    val cameraId: String = "",
    val cameraLabel: String = "",
    val resolution: String = "1280x720","""

replacement = """data class LiveCameraStats(
    val cameraId: String = "",
    val cameraLabel: String = "",
    val logicalCameraId: String? = null,
    val physicalCameraId: String? = null,
    val lensFacing: String = "",
    val hardwareLevel: String = "",
    val hasRaw: Boolean = false,
    val configuredFpsRange: String = "",
    val resolution: String = "1280x720","""

if target in content:
    content = content.replace(target, replacement)
    with open('./app/src/main/java/com/example/camera/CameraModels.kt', 'w') as f:
        f.write(content)
    print("Success")
else:
    print("Target not found")
