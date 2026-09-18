import re

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'r') as f:
    content = f.read()

start_cam = """    fun startCameraStream() {
        val camera = _selectedCamera.value
        if (camera == null) {
            Log.e(TAG, "CAMERA_UNAVAILABLE: No camera selected")
            return
        }

        cameraAcquisition.startCameraStream(camera, deviceId)"""
content = re.sub(r'    fun startCameraStream\(\) \{.*?cameraAcquisition\.startCameraStream\(camera, deviceId\)', start_cam, content, flags=re.DOTALL)

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'w') as f:
    f.write(content)
