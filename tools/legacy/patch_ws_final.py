import re

def fix_param(file_path):
    with open(file_path, 'r') as f:
        content = f.read()

    # The parameter was declared as `url` in connect() for Camera and Control.
    # But earlier I replaced `Connected to $url` with `Connected to $cameraUrl`.
    # Let's change the parameter to `cameraUrl` or `controlUrl` properly.
    if "CameraWebSocket" in content:
        content = content.replace("fun connect(url: String, helloJson: String? = null)", "fun connect(cameraUrl: String, helloJson: String? = null)")
    elif "ControlWebSocket" in content:
        content = content.replace("fun connect(url: String, helloJson: String? = null)", "fun connect(controlUrl: String, helloJson: String? = null)")

    with open(file_path, 'w') as f:
        f.write(content)

fix_param('./app/src/main/java/com/example/camera/CameraWebSocketClient.kt')
fix_param('./app/src/main/java/com/example/camera/ControlWebSocketClient.kt')
