import re

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'r') as f:
    content = f.read()

# Add getBaseUrl function
base_url_func = """
    private fun getBaseUrl(rawUrl: String): String {
        var base = rawUrl.trimEnd('/')
        if (base.endsWith("/sensors")) base = base.removeSuffix("/sensors")
        if (base.endsWith("/camera")) base = base.removeSuffix("/camera")
        if (base.endsWith("/control")) base = base.removeSuffix("/control")
        return base
    }
"""
if "getBaseUrl" not in content:
    content = content.replace("    private fun deriveCameraWsUrl(sensorWsUrl: String): String {\n        return if (sensorWsUrl.contains(\"/sensors\")) {\n            sensorWsUrl.replace(\"/sensors\", \"/camera\")\n        } else {\n            sensorWsUrl.trimEnd('/') + \"/camera\"\n        }\n    }", base_url_func)
else:
    # already exists, maybe remove deriveCameraWsUrl
    pass

# Patch connect
connect_sig = r'    fun connect\(url: String, discoveredLab: DiscoveredVirtualLab\? = null\) \{'
new_connect = """    fun connect(url: String, discoveredLab: DiscoveredVirtualLab? = null) {
        val baseUrl = getBaseUrl(url)
        val sensorUrl = "$baseUrl/sensors"
        
        connectionJob?.cancel()
        _connectedEndpoint.value = sensorUrl
        if (discoveredLab != null) {
            networkDiagnosticsManager.updateDiscoveredService(discoveredLab)
        } else {
            networkDiagnosticsManager.updateManualUrl(url)
        }

        val sensorsHello = Json.encodeToString(ChannelHelloMessage(deviceId = deviceId, channel = "sensors"))
        connectionJob = webSocketClient.connect(sensorUrl, sensorsHello).onEach {"""
content = re.sub(r'    fun connect\(url: String, discoveredLab: DiscoveredVirtualLab\? = null\) \{\n        connectionJob\?\.cancel\(\)\n        _connectedEndpoint\.value = url\n        if \(discoveredLab != null\) \{\n            networkDiagnosticsManager\.updateDiscoveredService\(discoveredLab\)\n        \} else \{\n            networkDiagnosticsManager\.updateManualUrl\(url\)\n        \}\n\n        val sensorsHello = Json\.encodeToString\(ChannelHelloMessage\(deviceId = deviceId, channel = "sensors"\)\)\n        connectionJob = webSocketClient\.connect\(url, sensorsHello\)\.onEach \{', new_connect, content, flags=re.DOTALL)

# Patch connectControlWsIfAppropriate
control_ws = """    private fun connectControlWsIfAppropriate(sensorUrl: String) {
        if (_controlWsState.value is ConnectionState.Connected || _controlWsState.value is ConnectionState.Connecting) return
        controlWsJob?.cancel()
        val controlUrl = "${getBaseUrl(sensorUrl)}/control"
        val controlHello = Json.encodeToString(ChannelHelloMessage(deviceId = deviceId, channel = "control"))
        controlWsJob = controlWebSocketClient.connect(controlUrl, controlHello).onEach { state ->
            _controlWsState.value = state
            Log.d("MainViewModel", "Control WS State: $state")
        }.launchIn(viewModelScope)
    }"""
content = re.sub(r'    private fun connectControlWsIfAppropriate\(sensorUrl: String\) \{.*?\n    \}', control_ws, content, flags=re.DOTALL)

# Patch connectCameraWsIfAppropriate
camera_ws = """    private fun connectCameraWsIfAppropriate(sensorUrl: String) {
        if (_cameraWsState.value is ConnectionState.Connected || _cameraWsState.value is ConnectionState.Connecting) return
        val cameraUrl = "${getBaseUrl(sensorUrl)}/camera"
        cameraWsJob?.cancel()
        val cameraHello = Json.encodeToString(ChannelHelloMessage(deviceId = deviceId, channel = "camera"))
        cameraWsJob = cameraWebSocketClient.connect(cameraUrl, cameraHello).onEach { state ->
            _cameraWsState.value = state
        }.launchIn(viewModelScope)
    }"""
content = re.sub(r'    private fun connectCameraWsIfAppropriate\(sensorUrl: String\) \{.*?\n    \}', camera_ws, content, flags=re.DOTALL)

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'w') as f:
    f.write(content)
