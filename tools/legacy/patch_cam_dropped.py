import re

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'r') as f:
    content = f.read()

content = content.replace("    private var droppedFrames = 0L", "    private var droppedFrames = 0L\n    fun incrementDroppedFrames() { droppedFrames++ }")

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'w') as f:
    f.write(content)
