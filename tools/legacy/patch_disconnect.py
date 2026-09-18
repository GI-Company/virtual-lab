with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'r') as f:
    content = f.read()

content = content.replace(
"""        cameraWsJob?.cancel()
        cameraWsJob = null""",
"""        cameraWsJob?.cancel()
        cameraWsJob = null
        controlWsJob?.cancel()
        controlWsJob = null""")

content = content.replace(
"""        _connectionState.value = ConnectionState.Disconnected
        _cameraWsState.value = ConnectionState.Disconnected""",
"""        _connectionState.value = ConnectionState.Disconnected
        _cameraWsState.value = ConnectionState.Disconnected
        _controlWsState.value = ConnectionState.Disconnected""")

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'w') as f:
    f.write(content)
