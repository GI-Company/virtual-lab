import re

def fix_url_var(file_path, var_name):
    with open(file_path, 'r') as f:
        content = f.read()
    content = content.replace("Connected to $url", f"Connected to ${var_name}")
    with open(file_path, 'w') as f:
        f.write(content)

fix_url_var('./app/src/main/java/com/example/camera/CameraWebSocketClient.kt', 'cameraUrl')
fix_url_var('./app/src/main/java/com/example/camera/ControlWebSocketClient.kt', 'controlUrl')
