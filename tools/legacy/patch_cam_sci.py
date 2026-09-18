import re

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'r') as f:
    content = f.read()

# Add scientificCaptureResults and processedRequests
fields = """    // Active Camera Session
    private var activeCameraDevice: CameraDevice? = null
    
    private val scientificCaptureResults = ConcurrentHashMap<Long, Pair<String, TotalCaptureResult>>()
    private val processedRequests = ConcurrentHashMap.newKeySet<String>()"""
content = content.replace("    // Active Camera Session\n    private var activeCameraDevice: CameraDevice? = null", fields)

# Modify captureScientificFrame
csf = """    private suspend fun captureScientificFrame(captureId: String, sendResult: (String) -> Unit) {
        val session = activeCaptureSession ?: run {
            sendResult(json.encodeToString(CameraControlResult(requestId = captureId, status = "FAILED", errorReason = "SESSION_NOT_ACTIVE")))
            return
        }
        val device = activeCameraDevice ?: return
        val stillReader = stillImageReader ?: return
        val handler = backgroundHandler ?: return
        
        if (!processedRequests.add(captureId)) {
            // Already processed or processing
            return
        }

        try {
            val captureBuilder = device.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE).apply {
                addTarget(stillReader.surface)
                applyControlParametersToBuilder(this)
                set(CaptureRequest.JPEG_QUALITY, 95.toByte())
                setTag(captureId)
            }

            kotlinx.coroutines.suspendCancellableCoroutine<Unit> { continuation ->
                try {
                    session.capture(captureBuilder.build(), object : CameraCaptureSession.CaptureCallback() {
                        override fun onCaptureCompleted(
                            session: CameraCaptureSession,
                            request: CaptureRequest,
                            result: TotalCaptureResult
                        ) {
                            latestCaptureResult = result
                            val timestamp = result.get(CaptureResult.SENSOR_TIMESTAMP)
                            if (timestamp != null) {
                                scientificCaptureResults[timestamp] = Pair(captureId, result)
                            }
                            sendResult(json.encodeToString(CameraControlResult(requestId = captureId, status = "APPLIED")))
                            if (continuation.isActive) continuation.resume(Unit)
                        }

                        override fun onCaptureFailed(
                            session: CameraCaptureSession,
                            request: CaptureRequest,
                            failure: CaptureFailure
                        ) {
                            sendResult(json.encodeToString(CameraControlResult(requestId = captureId, status = "FAILED", errorReason = "HAL_REJECTED")))
                            processedRequests.remove(captureId)
                            if (continuation.isActive) continuation.resume(Unit)
                        }
                    }, handler)
                } catch (e: Exception) {
                    if (continuation.isActive) continuation.resumeWithException(e)
                }
            }
        } catch (e: Exception) {
            sendResult(json.encodeToString(CameraControlResult(requestId = captureId, status = "FAILED", errorReason = e.message ?: "UNKNOWN")))
            processedRequests.remove(captureId)
        }
    }"""
content = re.sub(r'    fun captureScientificFrame\(captureId: String\? = null\) \{.*?\n    \}', csf, content, flags=re.DOTALL)

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'w') as f:
    f.write(content)
