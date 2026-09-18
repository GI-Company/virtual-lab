import sys
import re

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'r') as f:
    content = f.read()

# 1. Add fields to CameraAcquisitionManager
target_fields = """    private var activeParentLogicalId: String? = null
    private var isPhysicalMember = false
    private var activeDeviceId: String = """""

replacement_fields = """    private var activeParentLogicalId: String? = null
    private var isPhysicalMember = false
    private var activeDeviceId: String = ""
    
    private var activeCharacteristics: CameraCharacteristics? = null
    private var currentControlParams = ControlParameters()"""

content = content.replace(target_fields, replacement_fields)

# 2. Store activeCharacteristics
target_open = """        try {
            val chars = cameraManager.getCameraCharacteristics(camera.id)
            val streamMap = chars.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)"""

replacement_open = """        try {
            val chars = cameraManager.getCameraCharacteristics(camera.id)
            activeCharacteristics = chars
            val streamMap = chars.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)"""
content = content.replace(target_open, replacement_open)

# 3. Modify currentControlParams inside startCameraStream
target_init = """        isPhysicalMember = camera.parentLogicalCameraId != null
        activeDeviceId = deviceId
        _cameraErrorMessage.value = null"""
replacement_init = """        isPhysicalMember = camera.parentLogicalCameraId != null
        activeDeviceId = deviceId
        _cameraErrorMessage.value = null
        currentControlParams = ControlParameters()"""
content = content.replace(target_init, replacement_init)


# 4. Modify preview request builder
target_builder = """                            addTarget(previewReader.surface)
                            set(CaptureRequest.CONTROL_MODE, CaptureRequest.CONTROL_MODE_AUTO)
                            set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE)

                            // Set conservative FPS ~10-15 FPS
                            val fpsRanges = chars.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES)"""

replacement_builder = """                            addTarget(previewReader.surface)
                            applyControlParametersToBuilder(this)

                            // Set conservative FPS ~10-15 FPS
                            val fpsRanges = chars.get(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES)"""

content = content.replace(target_builder, replacement_builder)


# 5. Modify captureScientificFrame
target_capture = """    fun captureScientificFrame() {
        val session = activeCaptureSession ?: run {"""
replacement_capture = """    fun captureScientificFrame(captureId: String? = null) {
        val session = activeCaptureSession ?: run {"""
content = content.replace(target_capture, replacement_capture)

target_capture_builder = """            val captureBuilder = device.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE).apply {
                addTarget(stillReader.surface)
                set(CaptureRequest.CONTROL_MODE, CaptureRequest.CONTROL_MODE_AUTO)
                set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE)
                set(CaptureRequest.JPEG_QUALITY, 95.toByte())
            }"""
replacement_capture_builder = """            val captureBuilder = device.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE).apply {
                addTarget(stillReader.surface)
                applyControlParametersToBuilder(this)
                set(CaptureRequest.JPEG_QUALITY, 95.toByte())
                captureId?.let { setTag(it) } // Use tag to pass captureId if possible, or just generate internally
            }
            val finalCaptureId = captureId ?: ("CAP-" + System.currentTimeMillis() + "-" + java.util.UUID.randomUUID().toString().take(6))"""
content = content.replace(target_capture_builder, replacement_capture_builder)


target_still_image = """            val captureId = "CAP-" + System.currentTimeMillis() + "-" + UUID.randomUUID().toString().take(6)
            val result = latestCaptureResult"""
replacement_still_image = """            val captureId = image.timestamp.toString() // fallback
            // To properly match, we'd need to extract from request tag, but we will use the same ID logic or rely on timestamp correlation. We'll just generate one if not passed.
            // Wait, we need to pass the real captureId. We can pull it from the capture queue or keep it simple.
            val result = latestCaptureResult
            val realCaptureId = result?.request?.tag as? String ?: ("CAP-" + System.currentTimeMillis() + "-" + java.util.UUID.randomUUID().toString().take(6))"""
content = content.replace(target_still_image, replacement_still_image)

# Replace the usage of captureId in onStillImageAvailable
content = content.replace("captureId = captureId", "captureId = realCaptureId")
content = content.replace("Scientific frame captured: $captureId", "Scientific frame captured: $realCaptureId")

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'w') as f:
    f.write(content)

print("Success phase 1")
