import re

with open('./app/src/main/java/com/example/acquisition/SensorAcquisitionManager.kt', 'r') as f:
    content = f.read()

# Add a class for SensorStreamState
stream_state_class = """
    data class SensorStreamState(
        var isStreamingPackets: Boolean = false,
        var deviceId: String = "",
        var sessionId: String = ""
    )

    private val streamStates = ConcurrentHashMap<SensorTypeClass, SensorStreamState>()
"""

content = content.replace("private val activeListeners = ConcurrentHashMap<SensorTypeClass, SensorEventListener>()", 
    "private val activeListeners = ConcurrentHashMap<SensorTypeClass, SensorEventListener>()\n" + stream_state_class)

# Fix imports if needed
if "import java.util.concurrent.ConcurrentHashMap" not in content:
    content = content.replace("import android.hardware.SensorManager", "import android.hardware.SensorManager\nimport java.util.concurrent.ConcurrentHashMap")


# modify startLivePreview
start_live = """    fun startLivePreview(sensorClass: SensorTypeClass) {
        if (!isSensorAvailable(sensorClass)) return
        registerListener(sensorClass)
    }"""
content = re.sub(r'    fun startLivePreview\(.*?\n    \}', start_live, content, flags=re.DOTALL)

# modify startCapture
start_cap = """    fun startCapture(
        selectedSensors: Set<SensorTypeClass>,
        deviceId: String,
        sessionId: String
    ) {
        for (sensorClass in selectedSensors) {
            if (isSensorAvailable(sensorClass)) {
                sequenceNumbers.putIfAbsent(sensorClass, AtomicLong(0L))
                streamStates.getOrPut(sensorClass) { SensorStreamState() }.apply {
                    this.isStreamingPackets = true
                    this.deviceId = deviceId
                    this.sessionId = sessionId
                }
                registerListener(sensorClass)
            }
        }
    }"""
content = re.sub(r'    fun startCapture\(.*?\n        \}\n    \}', start_cap, content, flags=re.DOTALL)


stop_cap = """    fun stopCapture() {
        // Disable streaming for all sensors but don't unregister them if they are still previewed
        val keys = streamStates.keys.toList()
        for (key in keys) {
            streamStates[key]?.isStreamingPackets = false
        }
    }"""
content = re.sub(r'    fun stopCapture\(\) \{.*?\n        \}\n    \}', stop_cap, content, flags=re.DOTALL)

# modify registerListener
reg_lis = """    private fun registerListener(
        sensorClass: SensorTypeClass
    ) {
        if (activeListeners.containsKey(sensorClass)) {
            // Already registered
            return
        }

        val sensor = sensorManager.getDefaultSensor(sensorClass.androidType) ?: return

        // Buffer for rate calculation (last 16 event timestamps in nanoseconds)
        val timestampsBuffer = LongArray(16) { 0L }
        rateTimestamps[sensorClass] = timestampsBuffer
        rateIndex[sensorClass] = 0

        val listener = object : SensorEventListener {
            override fun onSensorChanged(event: SensorEvent) {
                val nowNs = event.timestamp
                val observedHz = calculateObservedRate(sensorClass, nowNs)

                // Update live state
                val currentCopy = event.values.clone()
                val reading = LiveSensorReading(
                    sensorClass = sensorClass,
                    values = currentCopy,
                    timestampNs = event.timestamp,
                    accuracy = event.accuracy,
                    observedHz = observedHz
                )

                val updatedMap = _liveReadings.value.toMutableMap()
                updatedMap[sensorClass] = reading
                _liveReadings.value = updatedMap

                // If streaming is enabled, construct and emit packet
                val state = streamStates[sensorClass]
                if (state?.isStreamingPackets == true) {
                    val seq = sequenceNumbers.getOrPut(sensorClass) { AtomicLong(0L) }.incrementAndGet()
                    val packet = createPacket(
                        sensorClass = sensorClass,
                        event = event,
                        deviceId = state.deviceId,
                        sessionId = state.sessionId,
                        sequence = seq
                    )
                    _packetStream.tryEmit(packet)
                }
            }

            override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}
        }

        activeListeners[sensorClass] = listener
        sensorManager.registerListener(listener, sensor, sensorClass.defaultDelay)
    }"""
content = re.sub(r'    private fun registerListener\(\n        sensorClass: SensorTypeClass,\n        isStreamingPackets: Boolean,\n        deviceId: String,\n        sessionId: String\n    \) \{.*?\n    \}', reg_lis, content, flags=re.DOTALL)


with open('./app/src/main/java/com/example/acquisition/SensorAcquisitionManager.kt', 'w') as f:
    f.write(content)
