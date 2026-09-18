import re

with open('./app/src/main/java/com/example/ui/SensorNodeApp.kt', 'r') as f:
    content = f.read()

# I want to wrap the `else { // Show discovery results }` block.
# Actually, I can just change the condition:
# if (connectedEndpoint != null) { ... } else if (transportMode != com.example.ui.TransportMode.USB_ADB) { ... } else { // Just show disconnected state for USB }

replacement = """            } else if (transportMode != com.example.ui.TransportMode.USB_ADB) {
                // Show discovery results"""
content = content.replace("            } else {\n                // Show discovery results", replacement)

# Add a disconnected view for USB
replacement2 = """                    }
                }
            } else {
                Surface(
                    color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f),
                    shape = MaterialTheme.shapes.medium,
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp)
                ) {
                    Column(
                        modifier = Modifier.fillMaxWidth().padding(12.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            "USB Development Session Offline",
                            style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.Bold),
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(Modifier.height(8.dp))
                        Text(
                            "Ensure `adb reverse tcp:8765 tcp:8765` is running and the Desktop is listening.",
                            style = MaterialTheme.typography.bodySmall,
                            textAlign = TextAlign.Center,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }"""
content = re.sub(r'                    \}\n                \}\n            \}\n        \}\n    \}\n\}', replacement2 + "\n        }\n    }\n}", content)

with open('./app/src/main/java/com/example/ui/SensorNodeApp.kt', 'w') as f:
    f.write(content)
