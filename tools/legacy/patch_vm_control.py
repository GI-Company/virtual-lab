import re

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'r') as f:
    content = f.read()

control_col = """        viewModelScope.launch {
            controlWebSocketClient.incomingMessages.collect { msg ->
                if (msg.deviceId != deviceId) {
                    controlWebSocketClient.sendResponse(Json.encodeToString(com.example.camera.CameraControlResult(
                        requestId = msg.requestId,
                        status = "REJECTED",
                        errorReason = "DEVICE_ID_MISMATCH"
                    )))
                    return@collect
                }
                cameraAcquisition.processControlCommand(msg) { responseJson: String ->
                    controlWebSocketClient.sendResponse(responseJson)
                }
            }
        }"""

content = re.sub(r'        viewModelScope\.launch \{\n            controlWebSocketClient\.incomingMessages\.collect \{ msg ->\n                cameraAcquisition\.processControlCommand\(msg\) \{ responseJson: String ->\n                    controlWebSocketClient\.sendResponse\(responseJson\)\n                \}\n            \}\n        \}', control_col, content, flags=re.DOTALL)

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'w') as f:
    f.write(content)
