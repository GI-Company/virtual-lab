import re

def patch_connect(file_path):
    with open(file_path, 'r') as f:
        content = f.read()
        
    content = re.sub(r'    fun connect\(.*Url: String\): Flow<ConnectionState> = callbackFlow \{',
                     r'    fun connect(url: String, helloJson: String? = null): Flow<ConnectionState> = callbackFlow {',
                     content)
    # The variable inside these might still be cameraUrl or controlUrl. We should just replace the signature.
    # Wait, earlier I replaced "Connected to $url" with "Connected to $cameraUrl", which uses the parameter name!
    # Let's fix the parameter names:
    if "cameraUrl" in content and "connect(cameraUrl: String" in content:
         content = content.replace("fun connect(cameraUrl: String)", "fun connect(cameraUrl: String, helloJson: String? = null)")
    elif "cameraUrl" in content and "connect(cameraUrl: String, helloJson: String? = null)" not in content:
         content = content.replace("fun connect(cameraUrl: String", "fun connect(cameraUrl: String, helloJson: String? = null")

    if "controlUrl" in content and "connect(controlUrl: String" in content:
         content = content.replace("fun connect(controlUrl: String)", "fun connect(controlUrl: String, helloJson: String? = null)")
    elif "controlUrl" in content and "connect(controlUrl: String, helloJson: String? = null)" not in content:
         content = content.replace("fun connect(controlUrl: String", "fun connect(controlUrl: String, helloJson: String? = null")

    with open(file_path, 'w') as f:
        f.write(content)

patch_connect('./app/src/main/java/com/example/camera/CameraWebSocketClient.kt')
patch_connect('./app/src/main/java/com/example/camera/ControlWebSocketClient.kt')
