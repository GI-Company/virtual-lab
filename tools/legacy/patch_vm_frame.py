import re

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'r') as f:
    content = f.read()

setup_cam = """    private fun setupCameraFrameForwarding() {
        cameraFrameForwardJob = cameraAcquisition.frameFlow.onEach { (meta, bytes) ->
            if (cameraWebSocketClient.isConnected()) {
                val sent = cameraWebSocketClient.sendBinaryFrame(meta, bytes)
                if (!sent && meta.messageType == "CAMERA_PREVIEW_FRAME") {
                    cameraAcquisition.incrementDroppedFrames()
                }
            }
        }.launchIn(viewModelScope)
    }"""
content = re.sub(r'    private fun setupCameraFrameForwarding\(\) \{.*?\n    \}', setup_cam, content, flags=re.DOTALL)

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'w') as f:
    f.write(content)
