import kotlinx.serialization.*
import kotlinx.serialization.json.*

@Serializable
data class AcquisitionMetadata(val exposure_ms: Int)

@Serializable
data class CameraMetadata(val gain: Double)

@Serializable
data class MeasurementPacket(
    val protocol_version: String,
    val message_type: String,
    val stream_id: String,
    val device_id: String,
    val device_timebase: Long,
    val sequence: Int,
    val sensor: String,
    val measurement_type: String,
    val values: Map<String, Double>,
    val units: Map<String, String>,
    val accuracy: Int,
    val acquisition_metadata: AcquisitionMetadata,
    val camera_metadata: CameraMetadata
)

fun main(args: Array<String>) {
    val packet = if (args.isNotEmpty()) {
        val inputJson = args[0]
        Json.decodeFromString<MeasurementPacket>(inputJson)
    } else {
        MeasurementPacket(
            protocol_version = "1.0",
            message_type = "measurement",
            stream_id = "STREAM-123",
            device_id = "DEVICE-456",
            device_timebase = 1234567890L,
            sequence = 42,
            sensor = "CMOS",
            measurement_type = "fluorescence",
            values = mapOf("channel1" to 1.23, "channel2" to 4.56),
            units = mapOf("channel1" to "RFU", "channel2" to "RFU"),
            accuracy = 95,
            acquisition_metadata = AcquisitionMetadata(10),
            camera_metadata = CameraMetadata(2.0)
        )
    }

    val jsonString = Json.encodeToString(packet)
    println(jsonString)
}
