import sys

with open('./app/src/main/java/com/example/ui/SensorNodeApp.kt', 'r') as f:
    content = f.read()

# Add Circle Icon
content = content.replace("import androidx.compose.material.icons.filled.CheckCircle", "import androidx.compose.material.icons.filled.CheckCircle\nimport androidx.compose.material.icons.filled.Circle")

channel_status_ui = """
@Composable
fun ChannelStatusRow(name: String, path: String, url: String, state: ConnectionState) {
    val stateText = when (state) {
        is ConnectionState.Connected -> "CONNECTED"
        is ConnectionState.Connecting -> "CONNECTING"
        is ConnectionState.Error -> "FAILED"
        is ConnectionState.Disconnected -> "DISCONNECTED"
    }
    val color = when (state) {
        is ConnectionState.Connected -> MaterialTheme.colorScheme.primary
        is ConnectionState.Connecting -> MaterialTheme.colorScheme.secondary
        is ConnectionState.Error -> MaterialTheme.colorScheme.error
        is ConnectionState.Disconnected -> MaterialTheme.colorScheme.outline
    }

    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text(name, style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold))
        Text(path, style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.Bold))
        Text(url, style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace), color = MaterialTheme.colorScheme.onSurfaceVariant)
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 2.dp)) {
            Icon(imageVector = Icons.Default.Circle, contentDescription = null, tint = color, modifier = Modifier.size(10.dp))
            Spacer(Modifier.width(6.dp))
            Text(stateText, style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold), color = color)
            if (state is ConnectionState.Error) {
                Spacer(Modifier.width(6.dp))
                Text(state.message, style = MaterialTheme.typography.labelSmall, color = color, maxLines = 1)
            }
        }
    }
}
"""

if "fun ChannelStatusRow" not in content:
    content = content + channel_status_ui

start_idx = content.find("            // Connected or connecting state")
end_idx = content.find("                is ConnectionState.Disconnected -> {")

if start_idx != -1 and end_idx != -1:
    old_block = content[start_idx:end_idx]
    
    new_block = """            // Connected or connecting state
            if (connectedEndpoint != null) {
                Surface(
                    color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f),
                    shape = MaterialTheme.shapes.medium,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.fillMaxWidth().padding(12.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Text("VIRTUAL LAB CHANNELS", style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.Bold))
                        
                        val baseUrl = connectedEndpoint.replace("/sensors", "").trimEnd('/')
                        ChannelStatusRow("Sensors", "/sensors", "$baseUrl/sensors", connectionState)
                        ChannelStatusRow("Imaging", "/camera", "$baseUrl/camera", cameraWsState)
                        ChannelStatusRow("Control", "/control", "$baseUrl/control", controlWsState)
                        
                        Button(
                            onClick = onDisconnect,
                            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                            modifier = Modifier.fillMaxWidth().padding(top = 8.dp)
                        ) {
                            Text("DISCONNECT")
                        }
                    }
                }
            } else {
"""
    content = content[:start_idx] + new_block + "                " + content[end_idx + 52:]
    
    # Wait, the closing brace for `else {` needs to be matched.
    # The original was:
    #             when (connectionState) {
    #                is ConnectionState.Connected -> { ... }
    #                is ConnectionState.Connecting -> { ... }
    #                is ConnectionState.Error -> { ... }
    #                is ConnectionState.Disconnected -> {
    #                    // Show discovery results
    #                    when (discoveryState) {
    # ...
    #                    }
    #                }
    #            }
    # 
    # If we replace the entire `when (connectionState) {` with `if (connectedEndpoint != null) { ... } else {` 
    # we just need to replace it correctly.

with open('./app/src/main/java/com/example/ui/SensorNodeApp.kt', 'w') as f:
    f.write(content)
