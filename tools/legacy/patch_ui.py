import re

with open('./app/src/main/java/com/example/ui/SensorNodeApp.kt', 'r') as f:
    content = f.read()

# Update VirtualLabCard signature
content = content.replace(
"""fun VirtualLabCard(
    discoveryState: DiscoveryState,
    connectionState: ConnectionState,""",
"""fun VirtualLabCard(
    discoveryState: DiscoveryState,
    connectionState: ConnectionState,
    cameraWsState: ConnectionState,
    controlWsState: ConnectionState,""")

# Update VirtualLabCard call in App Content
content = content.replace(
"""                VirtualLabCard(
                    discoveryState = discoveryState,
                    connectionState = connectionState,
                    connectedEndpoint = connectedEndpoint,""",
"""                VirtualLabCard(
                    discoveryState = discoveryState,
                    connectionState = connectionState,
                    cameraWsState = cameraWsState,
                    controlWsState = controlWsState,
                    connectedEndpoint = connectedEndpoint,""")

with open('./app/src/main/java/com/example/ui/SensorNodeApp.kt', 'w') as f:
    f.write(content)
