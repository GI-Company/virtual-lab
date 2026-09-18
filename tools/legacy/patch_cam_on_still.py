import re

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'r') as f:
    content = f.read()

on_still = """    private fun onStillImageAvailable(reader: ImageReader) {
        val image = try {
            reader.acquireLatestImage()
        } catch (e: Exception) {
            null
        } ?: return

        try {
            val planes = image.planes
            if (planes.isEmpty()) return

            val buffer = planes[0].buffer
            val bytes = ByteArray(buffer.remaining())
            buffer.get(bytes)

            val timestamp = image.timestamp
            val matchedResult = scientificCaptureResults.remove(timestamp)
            val result = matchedResult?.second
            val realCaptureId = matchedResult?.first ?: ("CAP-" + System.currentTimeMillis() + "-" + java.util.UUID.randomUUID().toString().take(6))
            
            val expTime = result?.get(CaptureResult.SENSOR_EXPOSURE_TIME)
            val iso = result?.get(CaptureResult.SENSOR_SENSITIVITY)
            val focalLen = result?.get(CaptureResult.LENS_FOCAL_LENGTH)
            val focusDist = result?.get(CaptureResult.LENS_FOCUS_DISTANCE)
            val timestampNs = result?.get(CaptureResult.SENSOR_TIMESTAMP) ?: image.timestamp

            val scientificFrame = ScientificCapturedFrame(
                captureId = realCaptureId,
                cameraId = activeCameraId,
                cameraLabel = activeCameraLabel,
                timestampNs = timestampNs,
                width = image.width,
                height = image.height,
                exposureTimeNs = expTime,
                iso = iso,
                focalLengthMm = focalLen,
                focusDistance = focusDist,
                jpegSizeBytes = bytes.size,
                jpegBytes = bytes
            )"""

content = re.sub(r'    private fun onStillImageAvailable\(reader: ImageReader\) \{.*?\n            val scientificFrame = ScientificCapturedFrame\(.*?jpegBytes = bytes\n            \)', on_still, content, flags=re.DOTALL)

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'w') as f:
    f.write(content)
