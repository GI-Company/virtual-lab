import re

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'r') as f:
    content = f.read()

# Make sure Json encode is available
if "import com.example.camera.ChannelHelloMessage" not in content:
    content = content.replace("import com.example.transport.ConnectionState", "import com.example.transport.ConnectionState\nimport com.example.camera.ChannelHelloMessage")

# Patch webSocketClient.connect(url)
content = content.replace(
    "connectionJob = webSocketClient.connect(url).onEach",
    """val sensorsHello = Json.encodeToString(ChannelHelloMessage(deviceId = deviceId, channel = "sensors"))
        connectionJob = webSocketClient.connect(url, sensorsHello).onEach"""
)

# Patch connectCameraWsIfAppropriate
content = content.replace(
    "cameraWsJob = cameraWebSocketClient.connect(cameraUrl).onEach",
    """val cameraHello = Json.encodeToString(ChannelHelloMessage(deviceId = deviceId, channel = "camera"))
        cameraWsJob = cameraWebSocketClient.connect(cameraUrl, cameraHello).onEach"""
)

# Patch connectControlWsIfAppropriate
content = content.replace(
    "controlWsJob = controlWebSocketClient.connect(controlUrl).onEach",
    """val controlHello = Json.encodeToString(ChannelHelloMessage(deviceId = deviceId, channel = "control"))
        controlWsJob = controlWebSocketClient.connect(controlUrl, controlHello).onEach"""
)

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'w') as f:
    f.write(content)

