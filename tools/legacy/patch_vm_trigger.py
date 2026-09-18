import re

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'r') as f:
    content = f.read()

content = content.replace("cameraAcquisition.captureScientificFrame(null)", "viewModelScope.launch { cameraAcquisition.captureScientificFrame(\"MANUAL-\" + java.util.UUID.randomUUID().toString().take(6)) {} }")

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'w') as f:
    f.write(content)

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'r') as f:
    content2 = f.read()
    
content2 = content2.replace("private suspend fun captureScientificFrame", "suspend fun captureScientificFrame")

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'w') as f:
    f.write(content2)
