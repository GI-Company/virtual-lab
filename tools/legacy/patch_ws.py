import re

def patch_ws(file_path):
    with open(file_path, 'r') as f:
        content = f.read()

    # Add helloJson param
    content = re.sub(r'    fun connect\(.*?url: String\): Flow<ConnectionState> = callbackFlow \{',
                     r'    fun connect(url: String, helloJson: String? = null): Flow<ConnectionState> = callbackFlow {',
                     content)

    # In onOpen, send helloJson
    on_open = """            override fun onOpen(webSocket: WebSocket, response: Response) {
                // OkHttp Lifecycle: OPEN
                appendLog("[OPEN] Connected to $url (HTTP ${response.code} ${response.message})")
                if (helloJson != null) {
                    webSocket.send(helloJson)
                }
                trySend(ConnectionState.Connected)
            }"""
    content = re.sub(r'            override fun onOpen\(webSocket: WebSocket, response: Response\) \{.*?\n                trySend\(ConnectionState\.Connected\)\n            \}', on_open, content, flags=re.DOTALL)
    
    # Task 3: CORRECT WEBSOCKET CONNECTED STATE
    # "CameraWebSocketClient.isConnected() and ControlWebSocketClient.isConnected() must represent a REAL OPEN WebSocket... Set true only in onOpen, false in onClosing, onClosed, onFailure, disconnect"
    # Wait, webSocket != null doesn't mean connected.
    if "isConnected(): Boolean" in content:
        # replace with checking if state is actually connected... wait, we can add a boolean flag `isOpen`
        content = content.replace("private var webSocket: WebSocket? = null", "private var webSocket: WebSocket? = null\n    private var isOpen: Boolean = false")
        content = content.replace("override fun onOpen(webSocket: WebSocket, response: Response) {", "override fun onOpen(webSocket: WebSocket, response: Response) {\n                isOpen = true")
        content = content.replace("override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {", "override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {\n                isOpen = false")
        content = content.replace("override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {", "override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {\n                isOpen = false")
        content = content.replace("override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {", "override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {\n                isOpen = false")
        content = content.replace("    fun isConnected(): Boolean {\n        return webSocket != null\n    }", "    fun isConnected(): Boolean {\n        return isOpen\n    }")
        content = content.replace("webSocket = null", "webSocket = null\n        isOpen = false")

    with open(file_path, 'w') as f:
        f.write(content)

patch_ws('./app/src/main/java/com/example/transport/WebSocketClient.kt')
patch_ws('./app/src/main/java/com/example/camera/CameraWebSocketClient.kt')
patch_ws('./app/src/main/java/com/example/camera/ControlWebSocketClient.kt')
