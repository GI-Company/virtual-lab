import sys

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'r') as f:
    content = f.read()

target = """fun processControlCommand(command: CameraControlMessage, sendResult: (Any) -> Unit) {"""
replacement = """import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

fun processControlCommand(command: CameraControlMessage, sendResult: (String) -> Unit) {"""
content = content.replace("fun processControlCommand", "private val json = kotlinx.serialization.json.Json { encodeDefaults = true }\n\n    fun processControlCommand")

# Now change all sendResult(xxx) to sendResult(json.encodeToString(xxx))

# Quick regex replacement for the 4 sendResult blocks
import re
content = re.sub(r"sendResult\((CameraControlResult\([\s\S]*?\))\)", r"sendResult(json.encodeToString(\1))", content)
content = re.sub(r"sendResult\((CameraCapabilitiesResponse\([\s\S]*?\))\)", r"sendResult(json.encodeToString(\1))", content)
content = re.sub(r"sendResult\((CameraStateResponse\([\s\S]*?\))\)", r"sendResult(json.encodeToString(\1))", content)

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'w') as f:
    f.write(content)
print("Success JSON serialization")
