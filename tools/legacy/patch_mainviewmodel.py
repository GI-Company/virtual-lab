import re

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'r') as f:
    content = f.read()

# Add _controlWsState and controlWsState
state_flow = """    private val _cameraWsState = MutableStateFlow<ConnectionState>(ConnectionState.Disconnected)
    val cameraWsState: StateFlow<ConnectionState> = _cameraWsState.asStateFlow()
"""
if "_controlWsState" not in content:
    content = content.replace(state_flow, state_flow + """
    private val _controlWsState = MutableStateFlow<ConnectionState>(ConnectionState.Disconnected)
    val controlWsState: StateFlow<ConnectionState> = _controlWsState.asStateFlow()
""")

# Modify connectControlWsIfAppropriate and connectCameraWsIfAppropriate to update their states independently of the main connectionState (if they don't already)
# Also change `connect` to call them immediately rather than waiting for main state.

connect_fn_regex = re.compile(r'    fun connect\(url: String, discoveredLab: DiscoveredVirtualLab\? = null\).*?networkDiagnosticsManager\.update\(\)\n        }\.launchIn\(viewModelScope\)\n    }', re.DOTALL)
new_connect_fn = """    fun connect(url: String, discoveredLab: DiscoveredVirtualLab? = null) {
        connectionJob?.cancel()
        _connectedEndpoint.value = url
        if (discoveredLab != null) {
            networkDiagnosticsManager.updateDiscoveredService(discoveredLab)
        } else {
            networkDiagnosticsManager.updateManualUrl(url)
        }

        connectionJob = webSocketClient.connect(url).onEach { state ->
            _connectionState.value = state
            when (state) {
                is ConnectionState.Connected -> {
                    _showLocalNetworkRestrictionWarning.value = false
                }
                is ConnectionState.Error -> {
                    val isNearbyGranted = permissionManager.isNearbyWifiDevicesGranted()
                    val isLanTarget = !isUsbDevelopmentUrl(url)
                    val errorLower = state.message.lowercase()
                    val isTimeoutOrUnreachable = errorLower.contains("timeout") ||
                            errorLower.contains("timed out") ||
                            errorLower.contains("failed to connect") ||
                            errorLower.contains("unreach") ||
                            errorLower.contains("ehostunreach")

                    if (isLanTarget && isTimeoutOrUnreachable && !isNearbyGranted) {
                        _showLocalNetworkRestrictionWarning.value = true
                    }
                }
                else -> {}
            }
            networkDiagnosticsManager.update()
        }.launchIn(viewModelScope)

        // Connect the other channels immediately and independently
        connectCameraWsIfAppropriate(url)
        connectControlWsIfAppropriate(url)
    }"""
content = connect_fn_regex.sub(new_connect_fn, content)

# update connectControlWsIfAppropriate
control_ws_regex = re.compile(r'    private fun connectControlWsIfAppropriate\(sensorUrl: String\) \{.*?\n        \}\n    \}', re.DOTALL)
new_control_ws = """    private fun connectControlWsIfAppropriate(sensorUrl: String) {
        controlWsJob?.cancel()
        val controlUrl = sensorUrl.replace("/sensors", "/control")
        controlWsJob = controlWebSocketClient.connect(controlUrl).onEach { state ->
            _controlWsState.value = state
            Log.d("MainViewModel", "Control WS State: $state")
        }.launchIn(viewModelScope)
        
        viewModelScope.launch {
            controlWebSocketClient.incomingMessages.collect { msg ->
                cameraAcquisition.processControlCommand(msg) { responseJson: String ->
                    controlWebSocketClient.sendResponse(responseJson)
                }
            }
        }
    }"""
content = control_ws_regex.sub(new_control_ws, content)

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'w') as f:
    f.write(content)

