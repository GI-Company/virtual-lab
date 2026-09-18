import re

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'r') as f:
    content = f.read()

# Remove the launch block from connectControlWsIfAppropriate
content = re.sub(r'        viewModelScope\.launch \{\n            controlWebSocketClient\.incomingMessages\.collect \{ msg ->\n                cameraAcquisition\.processControlCommand\(msg\) \{ responseJson: String ->\n                    controlWebSocketClient\.sendResponse\(responseJson\)\n                \}\n            \}\n        \}', '', content)

# Add it to the end of `init` block
init_end = """        if (cameraPermissionManager.isCameraPermissionGranted()) {
            refreshCameraInventory()
        }

        viewModelScope.launch {
            controlWebSocketClient.incomingMessages.collect { msg ->
                cameraAcquisition.processControlCommand(msg) { responseJson: String ->
                    controlWebSocketClient.sendResponse(responseJson)
                }
            }
        }
    }"""
content = re.sub(r'        if \(cameraPermissionManager\.isCameraPermissionGranted\(\)\) \{\n            refreshCameraInventory\(\)\n        \}\n    \}', init_end, content)

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'w') as f:
    f.write(content)
