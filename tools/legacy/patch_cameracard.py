import sys

with open('./app/src/main/java/com/example/ui/CameraCard.kt', 'r') as f:
    content = f.read()

target = """                Column(
                    modifier = Modifier.padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    MetricRow(label = "Resolution", value = liveStats.resolution)
                    MetricRow(label = "Observed FPS", value = "${liveStats.observedFps} FPS")"""

replacement = """                Column(
                    modifier = Modifier.padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    MetricRow(label = "Camera2 ID", value = liveStats.cameraId)
                    MetricRow(label = "Logical Parent", value = liveStats.logicalCameraId ?: "N/A")
                    MetricRow(label = "Physical ID", value = liveStats.physicalCameraId ?: "N/A")
                    MetricRow(label = "Lens Facing", value = liveStats.lensFacing)
                    MetricRow(label = "Hardware Level", value = liveStats.hardwareLevel)
                    MetricRow(label = "RAW Capability", value = if (liveStats.hasRaw) "SUPPORTED" else "NOT SUPPORTED")
                    MetricRow(label = "Configured FPS", value = liveStats.configuredFpsRange)
                    MetricRow(label = "Resolution", value = liveStats.resolution)
                    MetricRow(label = "Observed FPS", value = "${liveStats.observedFps} FPS")"""

if target in content:
    content = content.replace(target, replacement)
    with open('./app/src/main/java/com/example/ui/CameraCard.kt', 'w') as f:
        f.write(content)
    print("Success")
else:
    print("Target not found")
