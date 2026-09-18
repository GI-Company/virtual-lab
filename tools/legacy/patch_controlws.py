import sys

with open('./app/src/main/java/com/example/camera/ControlWebSocketClient.kt', 'r') as f:
    content = f.read()

target = """    inline fun <reified T> sendResponse(response: T): Boolean {
        val ws = webSocket ?: return false
        return try {
            val jsonString = json.encodeToString(response)
            ws.send(jsonString)
        } catch (e: Exception) {
            Log.e(TAG, "Failed sending control response", e)
            false
        }
    }"""
replacement = """    fun sendResponse(jsonString: String): Boolean {
        val ws = webSocket ?: return false
        return ws.send(jsonString)
    }"""

content = content.replace(target, replacement)
with open('./app/src/main/java/com/example/camera/ControlWebSocketClient.kt', 'w') as f:
    f.write(content)

