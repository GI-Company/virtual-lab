def replace_append_log(filepath, tag):
    with open(filepath, 'r') as f:
        content = f.read()
    
    content = content.replace(
        'val formatted = "[$timestamp] $line"',
        f'val formatted = "[$timestamp] [{tag}] $line"'
    )
    with open(filepath, 'w') as f:
        f.write(content)

replace_append_log('./app/src/main/java/com/example/transport/WebSocketClient.kt', 'SENSORS')
replace_append_log('./app/src/main/java/com/example/camera/CameraWebSocketClient.kt', 'CAMERA')
replace_append_log('./app/src/main/java/com/example/camera/ControlWebSocketClient.kt', 'CONTROL')
