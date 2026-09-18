import re

with open('./app/src/main/java/com/example/camera/CameraModels.kt', 'r') as f:
    content = f.read()

channel_hello = """
@Serializable
data class ChannelHelloMessage(
    @SerialName("schema_version") val schemaVersion: String = "1",
    @SerialName("message_type") val messageType: String = "CHANNEL_HELLO",
    @SerialName("device_id") val deviceId: String,
    val channel: String
)
"""
if "ChannelHelloMessage" not in content:
    content = content + channel_hello
    
    with open('./app/src/main/java/com/example/camera/CameraModels.kt', 'w') as f:
        f.write(content)
