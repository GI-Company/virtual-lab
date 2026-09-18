import sys

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'r') as f:
    content = f.read()

methods = """
    private fun applyControlParametersToBuilder(builder: CaptureRequest.Builder) {
        val params = currentControlParams
        
        // Base auto mode if no manual controls are specified
        builder.set(CaptureRequest.CONTROL_MODE, CaptureRequest.CONTROL_MODE_AUTO)

        // Focus
        when (params.afMode) {
            "OFF", "MANUAL" -> {
                builder.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_OFF)
                params.focusDistanceDiopters?.let {
                    builder.set(CaptureRequest.LENS_FOCUS_DISTANCE, it)
                }
            }
            "AUTO" -> builder.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_AUTO)
            "MACRO" -> builder.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_MACRO)
            "CONTINUOUS_VIDEO" -> builder.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_VIDEO)
            "CONTINUOUS_PICTURE" -> builder.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE)
            "EDOF" -> builder.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_EDOF)
            else -> builder.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE)
        }

        // Exposure
        when (params.aeMode) {
            "OFF", "MANUAL" -> {
                builder.set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_OFF)
                params.exposureTimeNs?.let {
                    builder.set(CaptureRequest.SENSOR_EXPOSURE_TIME, it)
                }
                params.iso?.let {
                    builder.set(CaptureRequest.SENSOR_SENSITIVITY, it)
                }
                params.frameDurationNs?.let {
                    builder.set(CaptureRequest.SENSOR_FRAME_DURATION, it)
                }
            }
            "ON" -> builder.set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON)
            "ON_AUTO_FLASH" -> builder.set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON_AUTO_FLASH)
            "ON_ALWAYS_FLASH" -> builder.set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON_ALWAYS_FLASH)
            "ON_AUTO_FLASH_REDEYE" -> builder.set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON_AUTO_FLASH_REDEYE)
            else -> builder.set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON)
        }
        
        params.aeCompensation?.let {
            builder.set(CaptureRequest.CONTROL_AE_EXPOSURE_COMPENSATION, it)
        }

        // AWB
        when (params.awbMode) {
            "OFF" -> builder.set(CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_OFF)
            "AUTO" -> builder.set(CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_AUTO)
            "INCANDESCENT" -> builder.set(CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_INCANDESCENT)
            "FLUORESCENT" -> builder.set(CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_FLUORESCENT)
            "WARM_FLUORESCENT" -> builder.set(CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_WARM_FLUORESCENT)
            "DAYLIGHT" -> builder.set(CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_DAYLIGHT)
            "CLOUDY_DAYLIGHT" -> builder.set(CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_CLOUDY_DAYLIGHT)
            "TWILIGHT" -> builder.set(CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_TWILIGHT)
            "SHADE" -> builder.set(CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_SHADE)
            else -> builder.set(CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_AUTO)
        }
        
        params.awbLock?.let {
            builder.set(CaptureRequest.CONTROL_AWB_LOCK, it)
        }
        
        // FPS Range
        params.fpsRange?.let { rangeStr ->
            val parts = rangeStr.split("-")
            if (parts.size == 2) {
                val min = parts[0].toIntOrNull()
                val max = parts[1].toIntOrNull()
                if (min != null && max != null) {
                    builder.set(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, android.util.Range(min, max))
                }
            }
        }
        
        // Stabilization
        when (params.opticalStabilization) {
            "ON" -> builder.set(CaptureRequest.LENS_OPTICAL_STABILIZATION_MODE, CaptureRequest.LENS_OPTICAL_STABILIZATION_MODE_ON)
            "OFF" -> builder.set(CaptureRequest.LENS_OPTICAL_STABILIZATION_MODE, CaptureRequest.LENS_OPTICAL_STABILIZATION_MODE_OFF)
        }
        
        when (params.videoStabilization) {
            "ON" -> builder.set(CaptureRequest.CONTROL_VIDEO_STABILIZATION_MODE, CaptureRequest.CONTROL_VIDEO_STABILIZATION_MODE_ON)
            "OFF" -> builder.set(CaptureRequest.CONTROL_VIDEO_STABILIZATION_MODE, CaptureRequest.CONTROL_VIDEO_STABILIZATION_MODE_OFF)
        }
        
        // Torch
        when (params.torch) {
            "ON" -> builder.set(CaptureRequest.FLASH_MODE, CaptureRequest.FLASH_MODE_TORCH)
            "OFF" -> builder.set(CaptureRequest.FLASH_MODE, CaptureRequest.FLASH_MODE_OFF)
        }
        
        // Digital Zoom (Crop Region)
        params.zoomRatio?.let { ratio ->
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.R) {
                builder.set(CaptureRequest.CONTROL_ZOOM_RATIO, ratio)
            }
        }
    }

    private fun updateRepeatingRequest() {
        val device = activeCameraDevice ?: return
        val session = activeCaptureSession ?: return
        val previewReader = previewImageReader ?: return
        val handler = backgroundHandler ?: return
        
        try {
            val requestBuilder = device.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW).apply {
                addTarget(previewReader.surface)
                applyControlParametersToBuilder(this)
            }
            session.setRepeatingRequest(
                requestBuilder.build(),
                object : CameraCaptureSession.CaptureCallback() {
                    override fun onCaptureCompleted(
                        session: CameraCaptureSession,
                        request: CaptureRequest,
                        result: TotalCaptureResult
                    ) {
                        latestCaptureResult = result
                    }
                    override fun onCaptureFailed(
                        session: CameraCaptureSession,
                        request: CaptureRequest,
                        failure: CaptureFailure
                    ) {
                        droppedFrames++
                    }
                },
                handler
            )
        } catch (e: Exception) {
            Log.e(TAG, "Failed to update repeating request", e)
        }
    }

    fun processControlCommand(command: CameraControlMessage, sendResult: (Any) -> Unit) {
        if (activeCameraDevice == null || activeCharacteristics == null) {
            sendResult(CameraControlResult(
                requestId = command.requestId,
                status = "FAILED",
                errorReason = "CAMERA_NOT_ACTIVE"
            ))
            return
        }
        
        when (command.messageType) {
            "GET_CAMERA_CAPABILITIES" -> {
                val caps = activeCharacteristics!!.getCameraCapabilitiesPayload()
                sendResult(CameraCapabilitiesResponse(
                    requestId = command.requestId,
                    deviceId = activeDeviceId,
                    cameraId = activeCameraId,
                    capabilities = caps
                ))
            }
            "GET_CAMERA_STATE" -> {
                sendResult(CameraStateResponse(
                    requestId = command.requestId,
                    deviceId = activeDeviceId,
                    cameraId = activeCameraId,
                    state = currentControlParams
                ))
            }
            "SET_CAMERA_CONTROLS" -> {
                val requested = command.parameters
                if (requested != null) {
                    val oldRes = currentControlParams.resolution
                    val newRes = requested.resolution ?: oldRes
                    
                    currentControlParams = currentControlParams.copy(
                        afMode = requested.afMode ?: currentControlParams.afMode,
                        focusDistanceDiopters = requested.focusDistanceDiopters ?: currentControlParams.focusDistanceDiopters,
                        aeMode = requested.aeMode ?: currentControlParams.aeMode,
                        exposureTimeNs = requested.exposureTimeNs ?: currentControlParams.exposureTimeNs,
                        iso = requested.iso ?: currentControlParams.iso,
                        frameDurationNs = requested.frameDurationNs ?: currentControlParams.frameDurationNs,
                        aeCompensation = requested.aeCompensation ?: currentControlParams.aeCompensation,
                        awbMode = requested.awbMode ?: currentControlParams.awbMode,
                        awbLock = requested.awbLock ?: currentControlParams.awbLock,
                        fpsRange = requested.fpsRange ?: currentControlParams.fpsRange,
                        resolution = newRes,
                        zoomRatio = requested.zoomRatio ?: currentControlParams.zoomRatio,
                        cropRegion = requested.cropRegion ?: currentControlParams.cropRegion,
                        opticalStabilization = requested.opticalStabilization ?: currentControlParams.opticalStabilization,
                        videoStabilization = requested.videoStabilization ?: currentControlParams.videoStabilization,
                        torch = requested.torch ?: currentControlParams.torch
                    )
                    
                    updateRepeatingRequest()
                    
                    sendResult(CameraControlResult(
                        requestId = command.requestId,
                        status = "APPLIED",
                        requested = requested,
                        applied = currentControlParams
                    ))
                }
            }
            "CAPTURE_SCIENTIFIC_FRAME" -> {
                captureScientificFrame(command.requestId)
            }
        }
    }
"""

if "processControlCommand" not in content:
    idx = content.rfind("}")
    content = content[:idx] + methods + "\n}"
    with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'w') as f:
        f.write(content)
    print("Success phase 2")
else:
    print("Already patched")
