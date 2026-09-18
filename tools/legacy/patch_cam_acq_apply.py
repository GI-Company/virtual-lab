import re

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'r') as f:
    content = f.read()

setter = """
    private fun <T> setKey(builder: CaptureRequest.Builder, key: CaptureRequest.Key<T>, value: T) {
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.P && isPhysicalMember && activeParentLogicalId != null) {
            try {
                // Not all keys are supported for physical camera requests.
                // CameraDevice.isSessionConfigurationSupported can check, but for now we try/catch or just set.
                // We'll just call setPhysicalCameraKey
                builder.setPhysicalCameraKey(key, value, activeCameraId)
            } catch (e: Exception) {
                Log.w(TAG, "Unsupported physical key: ${key.name}")
            }
        } else {
            builder.set(key, value)
        }
    }
    
    private fun applyControlParametersToBuilder(builder: CaptureRequest.Builder) {
        val params = currentControlParams
        
        // Base auto mode if no manual controls are specified
        setKey(builder, CaptureRequest.CONTROL_MODE, CaptureRequest.CONTROL_MODE_AUTO)

        // Focus
        when (params.afMode) {
            "OFF", "MANUAL" -> {
                setKey(builder, CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_OFF)
                params.focusDistanceDiopters?.let {
                    setKey(builder, CaptureRequest.LENS_FOCUS_DISTANCE, it)
                }
            }
            "AUTO" -> setKey(builder, CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_AUTO)
            "MACRO" -> setKey(builder, CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_MACRO)
            "CONTINUOUS_VIDEO" -> setKey(builder, CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_VIDEO)
            "CONTINUOUS_PICTURE" -> setKey(builder, CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE)
            "EDOF" -> setKey(builder, CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_EDOF)
            else -> setKey(builder, CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE)
        }

        // Exposure
        when (params.aeMode) {
            "OFF", "MANUAL" -> {
                setKey(builder, CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_OFF)
                params.exposureTimeNs?.let {
                    setKey(builder, CaptureRequest.SENSOR_EXPOSURE_TIME, it)
                }
                params.iso?.let {
                    setKey(builder, CaptureRequest.SENSOR_SENSITIVITY, it)
                }
                params.frameDurationNs?.let {
                    setKey(builder, CaptureRequest.SENSOR_FRAME_DURATION, it)
                }
            }
            "ON" -> setKey(builder, CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON)
            "ON_AUTO_FLASH" -> setKey(builder, CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON_AUTO_FLASH)
            "ON_ALWAYS_FLASH" -> setKey(builder, CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON_ALWAYS_FLASH)
            "ON_AUTO_FLASH_REDEYE" -> setKey(builder, CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON_AUTO_FLASH_REDEYE)
            else -> setKey(builder, CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON)
        }

        params.aeCompensation?.let {
            setKey(builder, CaptureRequest.CONTROL_AE_EXPOSURE_COMPENSATION, it)
        }

        // AWB
        when (params.awbMode) {
            "OFF" -> setKey(builder, CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_OFF)
            "AUTO" -> setKey(builder, CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_AUTO)
            "INCANDESCENT" -> setKey(builder, CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_INCANDESCENT)
            "FLUORESCENT" -> setKey(builder, CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_FLUORESCENT)
            "WARM_FLUORESCENT" -> setKey(builder, CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_WARM_FLUORESCENT)
            "DAYLIGHT" -> setKey(builder, CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_DAYLIGHT)
            "CLOUDY_DAYLIGHT" -> setKey(builder, CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_CLOUDY_DAYLIGHT)
            "TWILIGHT" -> setKey(builder, CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_TWILIGHT)
            "SHADE" -> setKey(builder, CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_SHADE)
            else -> setKey(builder, CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_AUTO)
        }

        params.awbLock?.let {
            setKey(builder, CaptureRequest.CONTROL_AWB_LOCK, it)
        }

        // FPS Range
        params.fpsRange?.let { fpsStr ->
            try {
                val parts = fpsStr.split("-")
                if (parts.size == 2) {
                    val lower = parts[0].toInt()
                    val upper = parts[1].toInt()
                    setKey(builder, CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, Range(lower, upper))
                }
            } catch (_: Exception) {}
        }
        
        // Zoom
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.R) {
            params.zoomRatio?.let {
                setKey(builder, CaptureRequest.CONTROL_ZOOM_RATIO, it)
            }
        }
        
        // Stabilization
        when (params.opticalStabilization) {
            "ON" -> setKey(builder, CaptureRequest.LENS_OPTICAL_STABILIZATION_MODE, CaptureRequest.LENS_OPTICAL_STABILIZATION_MODE_ON)
            "OFF" -> setKey(builder, CaptureRequest.LENS_OPTICAL_STABILIZATION_MODE, CaptureRequest.LENS_OPTICAL_STABILIZATION_MODE_OFF)
        }
        when (params.videoStabilization) {
            "ON" -> setKey(builder, CaptureRequest.CONTROL_VIDEO_STABILIZATION_MODE, CaptureRequest.CONTROL_VIDEO_STABILIZATION_MODE_ON)
            "OFF" -> setKey(builder, CaptureRequest.CONTROL_VIDEO_STABILIZATION_MODE, CaptureRequest.CONTROL_VIDEO_STABILIZATION_MODE_OFF)
        }
        
        // Torch
        when (params.torch) {
            "ON", "TORCH" -> setKey(builder, CaptureRequest.FLASH_MODE, CaptureRequest.FLASH_MODE_TORCH)
            "OFF" -> setKey(builder, CaptureRequest.FLASH_MODE, CaptureRequest.FLASH_MODE_OFF)
        }
    }"""
content = re.sub(r'    private fun applyControlParametersToBuilder\(builder: CaptureRequest\.Builder\) \{.*?\n    \}', setter, content, flags=re.DOTALL)

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'w') as f:
    f.write(content)
