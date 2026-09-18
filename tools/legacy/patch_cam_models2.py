import re

with open('./app/src/main/java/com/example/camera/CameraModels.kt', 'r') as f:
    content = f.read()

models = """
@Serializable
data class CameraInventoryResponse(
    @SerialName("schema_version") val schemaVersion: String = "1",
    @SerialName("message_type") val messageType: String = "CAMERA_INVENTORY",
    @SerialName("request_id") val requestId: String,
    @SerialName("device_id") val deviceId: String,
    @SerialName("cameras") val cameras: List<DiscoveredCamera>
)
"""
if "CameraInventoryResponse" not in content:
    # wait, DiscoveredCamera is not @Serializable!
    # Let's add @Serializable to DiscoveredCamera, CameraFacing, ConcurrentCameraGroup, etc.
    content = content.replace("data class DiscoveredCamera", "@Serializable\ndata class DiscoveredCamera")
    content = content.replace("enum class CameraFacing", "@Serializable\nenum class CameraFacing")
    content = content.replace("data class ConcurrentCameraGroup", "@Serializable\ndata class ConcurrentCameraGroup")
    content = content + models
    
    with open('./app/src/main/java/com/example/camera/CameraModels.kt', 'w') as f:
        f.write(content)
