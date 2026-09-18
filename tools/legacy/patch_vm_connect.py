import re

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'r') as f:
    content = f.read()

conn = """                is ConnectionState.Connected -> {
                    _showLocalNetworkRestrictionWarning.value = false
                    sensorManager.startCapture(_selectedCaptureSensors.value, deviceId, _sessionId.value)
                }"""
content = re.sub(r'                is ConnectionState\.Connected -> \{\n                    _showLocalNetworkRestrictionWarning\.value = false\n                \}', conn, content)

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'w') as f:
    f.write(content)
