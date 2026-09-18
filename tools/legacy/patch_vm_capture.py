import re

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'r') as f:
    content = f.read()

content = content.replace(
    "fun captureScientificFrame() {\n        cameraAcquisition.captureScientificFrame()\n    }",
    """fun captureScientificFrame() {
        viewModelScope.launch {
            cameraAcquisition.captureScientificFrame("MANUAL-" + java.util.UUID.randomUUID().toString().take(6)) {}
        }
    }"""
)

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'w') as f:
    f.write(content)
