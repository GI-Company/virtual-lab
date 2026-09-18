import re

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'r') as f:
    content = f.read()

# Add suspend to processControlCommand
content = content.replace("fun processControlCommand(command: CameraControlMessage, sendResult: (String) -> Unit)", "suspend fun processControlCommand(command: CameraControlMessage, sendResult: (String) -> Unit)")
content = content.replace("fun processControlCommand(command: CameraControlMessage, sendResult: suspend (String) -> Unit)", "suspend fun processControlCommand(command: CameraControlMessage, sendResult: (String) -> Unit)")

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'w') as f:
    f.write(content)
