import re

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'r') as f:
    content = f.read()

# patch setupPacketForwarding
spf = """    private fun setupPacketForwarding() {
        packetForwardJob = sensorManager.packetStream.onEach { packet ->
            if (_connectionState.value is ConnectionState.Connected) {
                try {
                    val json = Json.encodeToString(packet)
                    val sent = webSocketClient.send(json)
                    if (sent) {
                        _streamedPacketsCount.value = _streamedPacketsCount.value + 1
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Error serializing or sending sensor packet: ${e.message}")
                }
            }
        }.launchIn(viewModelScope)
    }"""
content = re.sub(r'    private fun setupPacketForwarding\(\) \{.*?\n    \}', spf, content, flags=re.DOTALL)


# patch toggleCaptureSensor
tcs = """    fun toggleCaptureSensor(sensorClass: SensorTypeClass) {
        val current = _selectedCaptureSensors.value.toMutableSet()
        if (current.contains(sensorClass)) {
            current.remove(sensorClass)
            sensorManager.stopCapture(setOf(sensorClass))
        } else {
            current.add(sensorClass)
            if (_connectionState.value is ConnectionState.Connected) {
                sensorManager.startCapture(setOf(sensorClass), deviceId, _sessionId.value)
            }
        }
        _selectedCaptureSensors.value = current
    }"""
content = re.sub(r'    fun toggleCaptureSensor\(.*?\n    \}', tcs, content, flags=re.DOTALL)

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'w') as f:
    f.write(content)

