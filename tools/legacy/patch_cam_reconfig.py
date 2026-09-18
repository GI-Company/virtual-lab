import re

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'r') as f:
    content = f.read()

content = content.replace("reconfigureSession()", "reconfigureSession(command.requestId, sendResult, requested)")

reconfig_func = """
    private suspend fun reconfigureSession(requestId: String, sendResult: (String) -> Unit, requested: ControlParameters) {
        val device = activeCameraDevice ?: return
        val chars = activeCharacteristics ?: return
        val streamMap = chars.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP) ?: return
        
        val jpegSizes = streamMap.getOutputSizes(ImageFormat.JPEG) ?: emptyArray()
        
        val reqRes = requested.resolution ?: currentControlParams.resolution
        val parts = reqRes?.split("x")
        val targetW = parts?.getOrNull(0)?.toIntOrNull() ?: 1280
        val targetH = parts?.getOrNull(1)?.toIntOrNull() ?: 720
        
        // Find matching size or closest
        val matchSize = jpegSizes.find { it.width == targetW && it.height == targetH } ?: selectPreviewSize(jpegSizes)
        
        // Stop repeating request
        activeCaptureSession?.stopRepeating()
        activeCaptureSession?.close()
        activeCaptureSession = null
        
        previewImageReader?.close()
        val handler = backgroundHandler ?: return
        
        previewImageReader = ImageReader.newInstance(
            matchSize.width,
            matchSize.height,
            ImageFormat.JPEG,
            3
        ).apply {
            setOnImageAvailableListener({ reader ->
                onPreviewImageAvailable(reader, activeDeviceId, matchSize)
            }, handler)
        }
        
        // Setup session
        kotlinx.coroutines.suspendCancellableCoroutine<Unit> { continuation ->
            try {
                device.createCaptureSession(
                    listOf(previewImageReader!!.surface, stillImageReader!!.surface),
                    object : CameraCaptureSession.StateCallback() {
                        override fun onConfigured(session: CameraCaptureSession) {
                            activeCaptureSession = session
                            kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.Default).launch {
                                updateRepeatingRequest(requestId, sendResult, requested)
                            }
                            if (continuation.isActive) continuation.resume(Unit)
                        }

                        override fun onConfigureFailed(session: CameraCaptureSession) {
                            sendResult(json.encodeToString(CameraControlResult(requestId = requestId, status = "FAILED", errorReason = "RECONFIGURATION_FAILED")))
                            if (continuation.isActive) continuation.resumeWithException(Exception("Reconfig failed"))
                        }
                    },
                    handler
                )
            } catch (e: Exception) {
                if (continuation.isActive) continuation.resumeWithException(e)
            }
        }
    }
"""
content = content.replace("    suspend fun processControlCommand", reconfig_func + "\n    suspend fun processControlCommand")

# Also import launch
content = content.replace("import kotlinx.coroutines.flow.asStateFlow", "import kotlinx.coroutines.flow.asStateFlow\nimport kotlinx.coroutines.launch")

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'w') as f:
    f.write(content)
