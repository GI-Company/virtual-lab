import re

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'r') as f:
    content = f.read()

content = content.replace("class CameraAcquisitionManager(\n    private val context: Context,\n    private val permissionManager: CameraPermissionManager,\n    private val thermalMonitor: DeviceThermalMonitor\n)",
"""class CameraAcquisitionManager(
    private val context: Context,
    private val permissionManager: CameraPermissionManager,
    private val thermalMonitor: DeviceThermalMonitor,
    private val cameraInventory: CameraHardwareInventory
)""")

with open('./app/src/main/java/com/example/camera/CameraAcquisitionManager.kt', 'w') as f:
    f.write(content)

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'r') as f:
    vm = f.read()

vm = vm.replace("val cameraAcquisition = CameraAcquisitionManager(application, cameraPermissionManager, thermalMonitor)",
"val cameraAcquisition = CameraAcquisitionManager(application, cameraPermissionManager, thermalMonitor, cameraInventory)")

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'w') as f:
    f.write(vm)
