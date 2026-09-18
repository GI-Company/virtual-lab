import re

with open('./app/src/main/java/com/example/camera/CameraWebSocketClient.kt', 'r') as f:
    content = f.read()

content = content.replace("if (ws.queueSize() > 2_000_000) { // e.g. 2MB", 'if (ws.queueSize() > 2_000_000 && metadata.messageType == "CAMERA_PREVIEW_FRAME") { // e.g. 2MB')

with open('./app/src/main/java/com/example/camera/CameraWebSocketClient.kt', 'w') as f:
    f.write(content)
