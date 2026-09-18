import re

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'r') as f:
    content = f.read()

# Replace updateRepeatingRequest
urr = """    private suspend fun updateRepeatingRequest(
        requestId: String,
        sendResult: (String) -> Unit,
        requested: ControlParameters
    ) {
        val device = activeCameraDevice ?: return
        val session = activeCaptureSession ?: return
        val previewReader = previewImageReader ?: return
        val handler = backgroundHandler ?: return
        
        try {
            val requestBuilder = device.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW).apply {
                addTarget(previewReader.surface)
                applyControlParametersToBuilder(this)
            }
            
            kotlinx.coroutines.suspendCancellableCoroutine<Unit> { continuation ->
                try {
                    session.setRepeatingRequest(
                        requestBuilder.build(),
                        object : CameraCaptureSession.CaptureCallback() {
                            private var appliedSent = false
                            
                            override fun onCaptureCompleted(
                                session: CameraCaptureSession,
                                request: CaptureRequest,
                                result: TotalCaptureResult
                            ) {
                                latestCaptureResult = result
                                if (!appliedSent) {
                                    appliedSent = true
                                    // Construct applied params
                                    val applied = ControlParameters(
                                        afMode = result.get(CaptureResult.CONTROL_AF_MODE)?.let { mode ->
                                            when(mode) {
                                                CaptureResult.CONTROL_AF_MODE_OFF -> "OFF"
                                                CaptureResult.CONTROL_AF_MODE_AUTO -> "AUTO"
                                                CaptureResult.CONTROL_AF_MODE_MACRO -> "MACRO"
                                                CaptureResult.CONTROL_AF_MODE_CONTINUOUS_VIDEO -> "CONTINUOUS_VIDEO"
                                                CaptureResult.CONTROL_AF_MODE_CONTINUOUS_PICTURE -> "CONTINUOUS_PICTURE"
                                                else -> "UNKNOWN"
                                            }
                                        } ?: "UNKNOWN",
                                        focusDistanceDiopters = result.get(CaptureResult.LENS_FOCUS_DISTANCE),
                                        aeMode = result.get(CaptureResult.CONTROL_AE_MODE)?.let { mode ->
                                            when(mode) {
                                                CaptureResult.CONTROL_AE_MODE_OFF -> "OFF"
                                                CaptureResult.CONTROL_AE_MODE_ON -> "ON"
                                                else -> "UNKNOWN"
                                            }
                                        } ?: "UNKNOWN",
                                        exposureTimeNs = result.get(CaptureResult.SENSOR_EXPOSURE_TIME),
                                        iso = result.get(CaptureResult.SENSOR_SENSITIVITY),
                                        frameDurationNs = result.get(CaptureResult.SENSOR_FRAME_DURATION),
                                        aeCompensation = result.get(CaptureResult.CONTROL_AE_EXPOSURE_COMPENSATION),
                                        awbMode = result.get(CaptureResult.CONTROL_AWB_MODE)?.let { mode ->
                                            when(mode) {
                                                CaptureResult.CONTROL_AWB_MODE_OFF -> "OFF"
                                                CaptureResult.CONTROL_AWB_MODE_AUTO -> "AUTO"
                                                else -> "UNKNOWN"
                                            }
                                        } ?: "UNKNOWN",
                                        awbLock = result.get(CaptureResult.CONTROL_AWB_LOCK),
                                        fpsRange = result.get(CaptureResult.CONTROL_AE_TARGET_FPS_RANGE)?.let { "${it.lower}-${it.upper}" } ?: "UNKNOWN",
                                        resolution = currentControlParams.resolution,
                                        zoomRatio = result.get(CaptureResult.CONTROL_ZOOM_RATIO),
                                        cropRegion = result.get(CaptureResult.SCALER_CROP_REGION)?.let { "${it.left},${it.top},${it.right},${it.bottom}" } ?: "UNKNOWN",
                                        opticalStabilization = result.get(CaptureResult.LENS_OPTICAL_STABILIZATION_MODE)?.let { mode ->
                                            when(mode) {
                                                CaptureResult.LENS_OPTICAL_STABILIZATION_MODE_OFF -> "OFF"
                                                CaptureResult.LENS_OPTICAL_STABILIZATION_MODE_ON -> "ON"
                                                else -> "UNKNOWN"
                                            }
                                        } ?: "UNKNOWN",
                                        videoStabilization = result.get(CaptureResult.CONTROL_VIDEO_STABILIZATION_MODE)?.let { mode ->
                                            when(mode) {
                                                CaptureResult.CONTROL_VIDEO_STABILIZATION_MODE_OFF -> "OFF"
                                                CaptureResult.CONTROL_VIDEO_STABILIZATION_MODE_ON -> "ON"
                                                else -> "UNKNOWN"
                                            }
                                        } ?: "UNKNOWN",
                                        torch = result.get(CaptureResult.FLASH_MODE)?.let { mode ->
                                            when(mode) {
                                                CaptureResult.FLASH_MODE_OFF -> "OFF"
                                                CaptureResult.FLASH_MODE_TORCH -> "TORCH"
                                                else -> "UNKNOWN"
                                            }
                                        } ?: "UNKNOWN"
                                    )
                                    sendResult(json.encodeToString(CameraControlResult(
                                        requestId = requestId,
                                        status = "APPLIED",
                                        requested = requested,
                                        applied = applied
                                    )))
                                    if (continuation.isActive) continuation.resume(Unit)
                                }
                            }
                            override fun onCaptureFailed(
                                session: CameraCaptureSession,
                                request: CaptureRequest,
                                failure: CaptureFailure
                            ) {
                                droppedFrames++
                                if (!appliedSent) {
                                    appliedSent = true
                                    sendResult(json.encodeToString(CameraControlResult(
                                        requestId = requestId,
                                        status = "FAILED",
                                        errorReason = "HAL_REJECTED"
                                    )))
                                    if (continuation.isActive) continuation.resume(Unit)
                                }
                            }
                        },
                        handler
                    )
                } catch (e: Exception) {
                    if (continuation.isActive) continuation.resumeWithException(e)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to update repeating request", e)
            sendResult(json.encodeToString(CameraControlResult(
                requestId = requestId,
                status = "FAILED",
                errorReason = e.message ?: "UNKNOWN"
            )))
        }
    }"""
content = re.sub(r'    private fun updateRepeatingRequest\(\) \{.*?\n    \}', urr, content, flags=re.DOTALL)

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'w') as f:
    f.write(content)
