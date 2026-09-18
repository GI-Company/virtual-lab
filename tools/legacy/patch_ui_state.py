import re

with open('./app/src/main/java/com/example/ui/SensorNodeApp.kt', 'r') as f:
    content = f.read()

# Add transportMode collection
content = content.replace(
    "    val connectedEndpoint by viewModel.connectedEndpoint.collectAsStateWithLifecycle()",
    """    val connectedEndpoint by viewModel.connectedEndpoint.collectAsStateWithLifecycle()
    val transportMode by viewModel.transportMode.collectAsStateWithLifecycle()"""
)

# Pass transportMode to VirtualLabCard
content = content.replace(
    "isUsbDevMode = viewModel.isUsbDevelopmentUrl(connectedEndpoint),",
    "transportMode = transportMode,\n                    usbBaseUrl = viewModel.usbBaseUrl.collectAsStateWithLifecycle().value,"
)

# Update VirtualLabCard signature
content = content.replace(
    "fun VirtualLabCard(\n    discoveryState: DiscoveryState,\n    connectionState: ConnectionState,\n    cameraWsState: ConnectionState,\n    controlWsState: ConnectionState,\n    connectedEndpoint: String?,\n    isUsbDevMode: Boolean,",
    """fun VirtualLabCard(
    discoveryState: DiscoveryState,
    connectionState: ConnectionState,
    cameraWsState: ConnectionState,
    controlWsState: ConnectionState,
    connectedEndpoint: String?,
    transportMode: com.example.ui.TransportMode,
    usbBaseUrl: String?,"""
)

# Update VirtualLabCard UI
# Current:
#             if (isUsbDevMode && connectionState is ConnectionState.Connected) {
#                 Surface(...) ... "USB / LOCAL DEVELOPMENT CONNECTION" ...
#             }
#
#             // Connected or connecting state
#             if (connectedEndpoint != null) { ...

replacement_ui = """
            // TRANSPORT MODE HEADER
            Row(
                modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "TRANSPORT MODE:",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.weight(1f)
                )
                Surface(
                    color = MaterialTheme.colorScheme.secondaryContainer,
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text(
                        text = if (transportMode == com.example.ui.TransportMode.USB_ADB) "USB DEVELOPMENT" else "LAN",
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                        style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold),
                        color = MaterialTheme.colorScheme.onSecondaryContainer
                    )
                }
            }

            if (transportMode == com.example.ui.TransportMode.USB_ADB) {
                Surface(
                    color = MaterialTheme.colorScheme.tertiaryContainer,
                    shape = MaterialTheme.shapes.small,
                    modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp)
                ) {
                    Row(
                        modifier = Modifier.padding(10.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = Icons.Default.Usb,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.onTertiaryContainer
                        )
                        Spacer(Modifier.width(8.dp))
                        Column {
                            Text(
                                "Base endpoint:",
                                style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.Bold),
                                color = MaterialTheme.colorScheme.onTertiaryContainer
                            )
                            Text(
                                "${usbBaseUrl ?: "ws://127.0.0.1:8765"}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onTertiaryContainer.copy(alpha = 0.8f)
                            )
                        }
                    }
                }
            }
"""

content = re.sub(
    r'            // USB Dev mode notice if active\n            if \(isUsbDevMode && connectionState is ConnectionState\.Connected\) \{.*?\n            \}\n',
    replacement_ui,
    content,
    flags=re.DOTALL
)

with open('./app/src/main/java/com/example/ui/SensorNodeApp.kt', 'w') as f:
    f.write(content)
