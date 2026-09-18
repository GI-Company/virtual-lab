import sys
import re

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'r') as f:
    content = f.read()

content = content.replace(
"""    private fun connectControlWsIfAppropriate(sensorUrl: String) {
        controlWsJob?.cancel()
        val controlUrl = sensorUrl.replace("/sensors", "/control")""",
"""    private fun connectControlWsIfAppropriate(sensorUrl: String) {
        if (_controlWsState.value is ConnectionState.Connected || _controlWsState.value is ConnectionState.Connecting) return
        controlWsJob?.cancel()
        val controlUrl = sensorUrl.replace("/sensors", "/control")""")

content = content.replace(
"""    private fun connectCameraWsIfAppropriate(sensorUrl: String) {
        val cameraUrl = deriveCameraWsUrl(sensorUrl)
        cameraWsJob?.cancel()""",
"""    private fun connectCameraWsIfAppropriate(sensorUrl: String) {
        if (_cameraWsState.value is ConnectionState.Connected || _cameraWsState.value is ConnectionState.Connecting) return
        val cameraUrl = deriveCameraWsUrl(sensorUrl)
        cameraWsJob?.cancel()""")

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'w') as f:
    f.write(content)
