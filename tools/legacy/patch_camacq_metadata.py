import sys

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'r') as f:
    content = f.read()

replacement_preview = """            val afModeInt = result?.get(CaptureResult.CONTROL_AF_MODE)
            val afStateInt = result?.get(CaptureResult.CONTROL_AF_STATE)
            val aeModeInt = result?.get(CaptureResult.CONTROL_AE_MODE)
            val aeStateInt = result?.get(CaptureResult.CONTROL_AE_STATE)
            val awbModeInt = result?.get(CaptureResult.CONTROL_AWB_MODE)
            val awbStateInt = result?.get(CaptureResult.CONTROL_AWB_STATE)
            val awbLockResult = result?.get(CaptureResult.CONTROL_AWB_LOCK)
            val frameDurationNs = result?.get(CaptureResult.SENSOR_FRAME_DURATION)
            val fpsRangeResult = result?.get(CaptureResult.CONTROL_AE_TARGET_FPS_RANGE)
            val fpsRangeStr = fpsRangeResult?.let { "${it.lower}-${it.upper}" }
            val cropRegion = result?.get(CaptureResult.SCALER_CROP_REGION)
            val zoomRatio = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.R) result?.get(CaptureResult.CONTROL_ZOOM_RATIO) else null
            
            val stabModeInt = result?.get(CaptureResult.LENS_OPTICAL_STABILIZATION_MODE)
            val vidStabModeInt = result?.get(CaptureResult.CONTROL_VIDEO_STABILIZATION_MODE)
            val stabStr = if (vidStabModeInt == CaptureResult.CONTROL_VIDEO_STABILIZATION_MODE_ON) "VIDEO_ON" 
                          else if (stabModeInt == CaptureResult.LENS_OPTICAL_STABILIZATION_MODE_ON) "OPTICAL_ON"
                          else "OFF"
                          
            val flashModeInt = result?.get(CaptureResult.FLASH_MODE)
            val torchStr = if (flashModeInt == CaptureResult.FLASH_MODE_TORCH) "ON" else "OFF"
            
            val metadata = CameraFrameMetadata(
                schemaVersion = "1",
                messageType = "CAMERA_PREVIEW_FRAME",
                deviceId = deviceId,
                cameraId = activeCameraId,
                logicalCameraId = activeParentLogicalId,
                physicalCameraId = if (isPhysicalMember) activeCameraId else null,
                frameSequence = frameSequence++,
                deviceTimestampNs = devTimestamp,
                width = image.width,
                height = image.height,
                pixelFormat = "JPEG",
                encoding = "JPEG",
                orientation = 0,
                lensFacing = activeLensFacingStr,
                focalLengthMm = focalLen,
                exposureTimeNs = expTime,
                sensorSensitivityIso = iso,
                focusDistance = focusDist,
                frameSizeBytes = bytes.size,
                scientificState = "MEASURED",
                acquisitionType = "CAMERA_FRAME",
                representation = "ISP_PROCESSED",
                frameDurationNs = frameDurationNs,
                afMode = afModeInt?.toString(),
                afState = afStateInt?.toString(),
                aeMode = aeModeInt?.toString(),
                aeState = aeStateInt?.toString(),
                awbMode = awbModeInt?.toString(),
                awbState = awbStateInt?.toString(),
                awbLock = awbLockResult,
                fpsRange = fpsRangeStr,
                cropRegion = cropRegion?.let { "${it.left},${it.top},${it.width()},${it.height()}" },
                zoomRatio = zoomRatio,
                stabilizationMode = stabStr,
                torchState = torchStr
            )"""

target_preview = """            val metadata = CameraFrameMetadata(
                schemaVersion = "1",
                messageType = "CAMERA_PREVIEW_FRAME",
                deviceId = deviceId,
                cameraId = activeCameraId,
                logicalCameraId = activeParentLogicalId,
                physicalCameraId = if (isPhysicalMember) activeCameraId else null,
                frameSequence = frameSequence++,
                deviceTimestampNs = devTimestamp,
                width = image.width,
                height = image.height,
                pixelFormat = "JPEG",
                encoding = "JPEG",
                orientation = 0,
                lensFacing = activeLensFacingStr,
                focalLengthMm = focalLen,
                exposureTimeNs = expTime,
                sensorSensitivityIso = iso,
                focusDistance = focusDist,
                frameSizeBytes = bytes.size,
                scientificState = "MEASURED",
                acquisitionType = "CAMERA_FRAME",
                representation = "ISP_PROCESSED"
            )"""
            
content = content.replace(target_preview, replacement_preview)

target_still = """            val metadata = CameraFrameMetadata(
                schemaVersion = "1",
                messageType = "CAMERA_SCIENTIFIC_FRAME",
                deviceId = activeDeviceId,
                cameraId = activeCameraId,
                logicalCameraId = activeParentLogicalId,
                physicalCameraId = if (isPhysicalMember) activeCameraId else null,
                frameSequence = frameSequence,
                deviceTimestampNs = timestampNs,
                width = image.width,
                height = image.height,
                pixelFormat = "JPEG",
                encoding = "JPEG",
                orientation = 0,
                lensFacing = activeLensFacingStr,
                focalLengthMm = focalLen,
                exposureTimeNs = expTime,
                sensorSensitivityIso = iso,
                focusDistance = focusDist,
                frameSizeBytes = bytes.size,
                scientificState = "MEASURED",
                acquisitionType = "CAMERA_FRAME",
                representation = "ISP_PROCESSED",
                captureId = realCaptureId
            )"""

replacement_still = replacement_preview.replace('"CAMERA_PREVIEW_FRAME"', '"CAMERA_SCIENTIFIC_FRAME"').replace('deviceId = deviceId,', 'deviceId = activeDeviceId,').replace('frameSequence = frameSequence++,', 'frameSequence = frameSequence,').replace('deviceTimestampNs = devTimestamp,', 'deviceTimestampNs = timestampNs,').replace('torchState = torchStr', 'torchState = torchStr,\n                captureId = realCaptureId')

content = content.replace(target_still, replacement_still)

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'w') as f:
    f.write(content)
print("Success Phase 3")

