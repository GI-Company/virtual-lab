import sys
import re

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'r') as f:
    content = f.read()

# 1. Imports
target_imports = """import com.example.camera.CameraWebSocketClient"""
replacement_imports = """import com.example.camera.CameraWebSocketClient
import com.example.camera.ControlWebSocketClient"""
content = content.replace(target_imports, replacement_imports)

# 2. Add client instance
target_val = """    val cameraWebSocketClient = CameraWebSocketClient()"""
replacement_val = """    val cameraWebSocketClient = CameraWebSocketClient()
    val controlWebSocketClient = ControlWebSocketClient()"""
content = content.replace(target_val, replacement_val)

# 3. Add job
target_job = """    private var cameraWsJob: Job? = null"""
replacement_job = """    private var cameraWsJob: Job? = null
    private var controlWsJob: Job? = null"""
content = content.replace(target_job, replacement_job)

# 4. Logs
target_logs = """    val cameraWsLogs: StateFlow<List<String>> = cameraWebSocketClient.connectionLogs"""
replacement_logs = """    val cameraWsLogs: StateFlow<List<String>> = cameraWebSocketClient.connectionLogs
    val controlWsLogs: StateFlow<List<String>> = controlWebSocketClient.connectionLogs"""
content = content.replace(target_logs, replacement_logs)

# 5. Method for Control WS
target_method = """    private fun connectCameraWsIfAppropriate(sensorUrl: String) {"""
replacement_method = """    private fun connectControlWsIfAppropriate(sensorUrl: String) {
        controlWsJob?.cancel()
        val controlUrl = sensorUrl.replace("/sensors", "/control")
        controlWsJob = controlWebSocketClient.connect(controlUrl).onEach { state ->
            Log.d("MainViewModel", "Control WS State: $state")
        }.launchIn(viewModelScope)
        
        viewModelScope.launch {
            controlWebSocketClient.incomingMessages.collect { msg ->
                cameraAcquisition.processControlCommand(msg) { responseJson ->
                    controlWebSocketClient.sendResponse(responseJson)
                }
            }
        }
    }

    private fun connectCameraWsIfAppropriate(sensorUrl: String) {"""
content = content.replace(target_method, replacement_method)

# 6. Call connection
target_call = """            connectCameraWsIfAppropriate(url)"""
replacement_call = """            connectCameraWsIfAppropriate(url)
            connectControlWsIfAppropriate(url)"""
content = content.replace(target_call, replacement_call)

target_call2 = """            connectCameraWsIfAppropriate(sensorUrl)"""
replacement_call2 = """            connectCameraWsIfAppropriate(sensorUrl)
            connectControlWsIfAppropriate(sensorUrl)"""
content = content.replace(target_call2, replacement_call2)

# 7. Disconnect
target_disconnect = """        cameraWebSocketClient.disconnect()"""
replacement_disconnect = """        cameraWebSocketClient.disconnect()
        controlWebSocketClient.disconnect()"""
content = content.replace(target_disconnect, replacement_disconnect)

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'w') as f:
    f.write(content)

print("Success MainViewModel")
