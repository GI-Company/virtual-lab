import re

with open('./app/src/main/java/com/example/acquisition/SensorAcquisitionManager.kt', 'r') as f:
    content = f.read()

sc = """    fun stopCapture(sensors: Set<SensorTypeClass>) {
        for (sensor in sensors) {
            streamStates[sensor]?.isStreamingPackets = false
        }
    }

    fun stopCapture() {
        val keys = streamStates.keys.toList()
        for (key in keys) {
            streamStates[key]?.isStreamingPackets = false
        }
    }"""
content = re.sub(r'    fun stopCapture\(\) \{.*?\n    \}', sc, content, flags=re.DOTALL)

with open('./app/src/main/java/com/example/acquisition/SensorAcquisitionManager.kt', 'w') as f:
    f.write(content)
