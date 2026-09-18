import sys
import re

with open('./app/src/main/java/com/example/camera/CameraModels.kt', 'r') as f:
    content = f.read()

# 1. Update CameraFrameMetadata
old_meta = """    @SerialName("exposure_time_ns") val exposureTimeNs: Long? = null,
    @SerialName("sensor_sensitivity_iso") val sensorSensitivityIso: Int? = null,
    @SerialName("focus_distance") val focusDistance: Float? = null,"""
new_meta = """    @SerialName("exposure_time_ns") val exposureTimeNs: Long? = null,
    @SerialName("sensor_sensitivity_iso") val sensorSensitivityIso: Int? = null,
    @SerialName("focus_distance") val focusDistance: Float? = null,
    @SerialName("frame_duration_ns") val frameDurationNs: Long? = null,
    @SerialName("af_mode") val afMode: String? = null,
    @SerialName("af_state") val afState: String? = null,
    @SerialName("ae_mode") val aeMode: String? = null,
    @SerialName("ae_state") val aeState: String? = null,
    @SerialName("awb_mode") val awbMode: String? = null,
    @SerialName("awb_state") val awbState: String? = null,
    @SerialName("awb_lock") val awbLock: Boolean? = null,
    @SerialName("fps_range") val fpsRange: String? = null,
    @SerialName("crop_region") val cropRegion: String? = null,
    @SerialName("zoom_ratio") val zoomRatio: Float? = null,
    @SerialName("stabilization_mode") val stabilizationMode: String? = null,
    @SerialName("torch_state") val torchState: String? = null,"""

if old_meta in content:
    content = content.replace(old_meta, new_meta)
else:
    print("Failed to patch CameraFrameMetadata")

# 2. Append new Control models
models = """
@Serializable
data class ControlParameters(
    @SerialName("af_mode") val afMode: String? = null,
    @SerialName("focus_distance_diopters") val focusDistanceDiopters: Float? = null,
    @SerialName("ae_mode") val aeMode: String? = null,
    @SerialName("exposure_time_ns") val exposureTimeNs: Long? = null,
    @SerialName("iso") val iso: Int? = null,
    @SerialName("frame_duration_ns") val frameDurationNs: Long? = null,
    @SerialName("ae_compensation") val aeCompensation: Int? = null,
    @SerialName("awb_mode") val awbMode: String? = null,
    @SerialName("awb_lock") val awbLock: Boolean? = null,
    @SerialName("fps_range") val fpsRange: String? = null,
    @SerialName("resolution") val resolution: String? = null,
    @SerialName("zoom_ratio") val zoomRatio: Float? = null,
    @SerialName("crop_region") val cropRegion: String? = null,
    @SerialName("optical_stabilization") val opticalStabilization: String? = null,
    @SerialName("video_stabilization") val videoStabilization: String? = null,
    @SerialName("torch") val torch: String? = null,
    @SerialName("stream_state") val streamState: String? = null
)

@Serializable
data class CameraControlMessage(
    @SerialName("schema_version") val schemaVersion: String = "1",
    @SerialName("message_type") val messageType: String,
    @SerialName("request_id") val requestId: String,
    @SerialName("device_id") val deviceId: String,
    @SerialName("camera_id") val cameraId: String? = null,
    @SerialName("logical_camera_id") val logicalCameraId: String? = null,
    @SerialName("physical_camera_id") val physicalCameraId: String? = null,
    @SerialName("timestamp_utc") val timestampUtc: Long = 0L,
    @SerialName("parameters") val parameters: ControlParameters? = null
)

@Serializable
data class CameraControlResult(
    @SerialName("schema_version") val schemaVersion: String = "1",
    @SerialName("message_type") val messageType: String = "CAMERA_CONTROL_RESULT",
    @SerialName("request_id") val requestId: String,
    @SerialName("status") val status: String,
    @SerialName("requested") val requested: ControlParameters? = null,
    @SerialName("applied") val applied: ControlParameters? = null,
    @SerialName("error_reason") val errorReason: String? = null
)

@Serializable
data class CameraCapabilitiesPayload(
    @SerialName("manual_focus_supported") val manualFocusSupported: Boolean,
    @SerialName("min_focus_distance") val minFocusDistance: Float?,
    @SerialName("available_af_modes") val availableAfModes: List<String>,
    @SerialName("manual_sensor_supported") val manualSensorSupported: Boolean,
    @SerialName("exposure_time_range") val exposureTimeRange: List<Long>?,
    @SerialName("iso_range") val isoRange: List<Int>?,
    @SerialName("frame_duration_range") val frameDurationRange: List<Long>?,
    @SerialName("available_ae_modes") val availableAeModes: List<String>,
    @SerialName("ae_compensation_range") val aeCompensationRange: List<Int>?,
    @SerialName("ae_compensation_step") val aeCompensationStep: Float?,
    @SerialName("available_awb_modes") val availableAwbModes: List<String>,
    @SerialName("awb_lock_supported") val awbLockSupported: Boolean,
    @SerialName("available_fps_ranges") val availableFpsRanges: List<String>,
    @SerialName("supported_resolutions") val supportedResolutions: List<String>,
    @SerialName("zoom_ratio_range") val zoomRatioRange: List<Float>?,
    @SerialName("optical_stabilization_modes") val opticalStabilizationModes: List<String>,
    @SerialName("video_stabilization_modes") val videoStabilizationModes: List<String>,
    @SerialName("flash_supported") val flashSupported: Boolean,
    @SerialName("raw_sensor_supported") val rawSensorSupported: Boolean,
    @SerialName("yuv_supported") val yuvSupported: Boolean
)

@Serializable
data class CameraCapabilitiesResponse(
    @SerialName("schema_version") val schemaVersion: String = "1",
    @SerialName("message_type") val messageType: String = "CAMERA_CAPABILITIES",
    @SerialName("request_id") val requestId: String,
    @SerialName("device_id") val deviceId: String,
    @SerialName("camera_id") val cameraId: String,
    @SerialName("capabilities") val capabilities: CameraCapabilitiesPayload
)

@Serializable
data class CameraStateResponse(
    @SerialName("schema_version") val schemaVersion: String = "1",
    @SerialName("message_type") val messageType: String = "CAMERA_STATE",
    @SerialName("request_id") val requestId: String,
    @SerialName("device_id") val deviceId: String,
    @SerialName("camera_id") val cameraId: String,
    @SerialName("state") val state: ControlParameters
)
"""

content += models

with open('./app/src/main/java/com/example/camera/CameraModels.kt', 'w') as f:
    f.write(content)

print("Success")
