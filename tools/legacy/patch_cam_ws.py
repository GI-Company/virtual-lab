import re

with open('./app/src/main/java/com/example/camera/CameraWebSocketClient.kt', 'r') as f:
    content = f.read()

send_binary = """    fun sendBinaryFrame(metadata: CameraFrameMetadata, jpegBytes: ByteArray): Boolean {
        val ws = webSocket ?: return false
        
        // Backpressure check
        if (ws.queueSize() > 2_000_000) { // e.g. 2MB
            // queue is too large, drop this preview frame
            return false
        }
        
        return try {
            val jsonString = Json.encodeToString(metadata)
            val jsonBytes = jsonString.toByteArray(Charsets.UTF_8)
            val totalSize = 4 + jsonBytes.size + jpegBytes.size

            val buffer = ByteBuffer.allocate(totalSize)
            buffer.order(ByteOrder.BIG_ENDIAN)
            buffer.putInt(jsonBytes.size)
            buffer.put(jsonBytes)
            buffer.put(jpegBytes)

            val byteString = buffer.array().toByteString(0, totalSize)
            ws.send(byteString)
        } catch (e: Exception) {
            Log.e(TAG, "Failed sending binary frame: ${e.message}", e)
            false
        }
    }"""
content = re.sub(r'    fun sendBinaryFrame\(.*?\n    \}', send_binary, content, flags=re.DOTALL)

with open('./app/src/main/java/com/example/camera/CameraWebSocketClient.kt', 'w') as f:
    f.write(content)
