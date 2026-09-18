import re

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'r') as f:
    content = f.read()

# Replace processControlCommand
pcc = """    suspend fun processControlCommand(command: CameraControlMessage, sendResult: (String) -> Unit) {
        when (command.messageType) {
            "GET_CAMERA_INVENTORY" -> {
                val cameras = cameraInventory.discoverCameras()
                sendResult(json.encodeToString(CameraInventoryResponse(
                    requestId = command.requestId,
                    deviceId = command.deviceId,
                    cameras = cameras
                )))
                return
            }
            "GET_CAMERA_CAPABILITIES" -> {
                val targetCameraId = command.cameraId ?: activeCameraId
                if (targetCameraId.isEmpty()) {
                    sendResult(json.encodeToString(CameraControlResult(
                        requestId = command.requestId,
                        status = "FAILED",
                        errorReason = "NO_CAMERA_TARGET"
                    )))
                    return
                }
                try {
                    val chars = cameraManager.getCameraCharacteristics(targetCameraId)
                    val caps = chars.getCameraCapabilitiesPayload()
                    sendResult(json.encodeToString(CameraCapabilitiesResponse(
                        requestId = command.requestId,
                        deviceId = command.deviceId,
                        cameraId = targetCameraId,
                        capabilities = caps
                    )))
                } catch (e: Exception) {
                    sendResult(json.encodeToString(CameraControlResult(
                        requestId = command.requestId,
                        status = "FAILED",
                        errorReason = "CAMERA_ACCESS_ERROR"
                    )))
                }
                return
            }
            "SELECT_CAMERA", "START_CAMERA_STREAM" -> {
                val targetCameraId = command.cameraId
                if (targetCameraId.isNullOrEmpty()) {
                    sendResult(json.encodeToString(CameraControlResult(
                        requestId = command.requestId,
                        status = "FAILED",
                        errorReason = "NO_CAMERA_TARGET"
                    )))
                    return
                }
                val camera = cameraInventory.discoverCameras().find { it.id == targetCameraId }
                if (camera == null) {
                    sendResult(json.encodeToString(CameraControlResult(
                        requestId = command.requestId,
                        status = "FAILED",
                        errorReason = "CAMERA_NOT_FOUND"
                    )))
                    return
                }
                startCameraStream(camera, command.deviceId)
                sendResult(json.encodeToString(CameraControlResult(
                    requestId = command.requestId,
                    status = "APPLIED"
                )))
                return
            }
            "STOP_CAMERA_STREAM" -> {
                stopCameraStream()
                sendResult(json.encodeToString(CameraControlResult(
                    requestId = command.requestId,
                    status = "APPLIED"
                )))
                return
            }
        }

        if (activeCameraDevice == null || activeCharacteristics == null) {
            sendResult(json.encodeToString(CameraControlResult(
                requestId = command.requestId,
                status = "FAILED",
                errorReason = "CAMERA_NOT_ACTIVE"
            )))
            return
        }
        
        when (command.messageType) {
            "GET_CAMERA_STATE" -> {
                sendResult(json.encodeToString(CameraStateResponse(
                    requestId = command.requestId,
                    deviceId = activeDeviceId,
                    cameraId = activeCameraId,
                    state = currentControlParams
                )))
            }
            "SET_CAMERA_CONTROLS" -> {
                val requested = command.parameters
                if (requested != null) {
                    val oldRes = currentControlParams.resolution
                    val newRes = requested.resolution ?: oldRes
                    
                    // Validate against capabilities
                    val caps = activeCharacteristics!!.getCameraCapabilitiesPayload()
                    // Check focus distance
                    if (requested.focusDistanceDiopters != null && caps.minFocusDistance != null) {
                        if (requested.focusDistanceDiopters > caps.minFocusDistance || requested.focusDistanceDiopters < 0.0f) {
                            sendResult(json.encodeToString(CameraControlResult(
                                requestId = command.requestId,
                                status = "REJECTED",
                                errorReason = "FOCUS_DISTANCE_OUT_OF_RANGE"
                            )))
                            return
                        }
                    }
                    
                    val needsReconfig = newRes != oldRes
                    
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
                    
                    if (needsReconfig) {
                        // TODO: Implement REAL resolution reconfiguration
                        sendResult(json.encodeToString(CameraControlResult(
                            requestId = command.requestId,
                            status = "RECONFIGURING"
                        )))
                        reconfigureSession()
                    } else {
                        sendResult(json.encodeToString(CameraControlResult(
                            requestId = command.requestId,
                            status = "APPLYING"
                        )))
                        updateRepeatingRequest(command.requestId, sendResult, requested)
                    }
                }
            }
            "CAPTURE_SCIENTIFIC_FRAME" -> {
                captureScientificFrame(command.requestId, sendResult)
            }
        }
    }"""
content = re.sub(r'    suspend fun processControlCommand\(command: CameraControlMessage, sendResult: \(String\) -> Unit\) \{.*?\n    \}', pcc, content, flags=re.DOTALL)

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'w') as f:
    f.write(content)
