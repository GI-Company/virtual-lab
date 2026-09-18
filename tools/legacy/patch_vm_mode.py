import re

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'r') as f:
    content = f.read()

# Add TransportMode
if "enum class TransportMode" not in content:
    content = content.replace("class MainViewModel(application: Application) : AndroidViewModel(application) {", """enum class TransportMode { LAN, USB_ADB }

class MainViewModel(application: Application) : AndroidViewModel(application) {""")

    mode_state = """    // Transport Mode
    private val _transportMode = MutableStateFlow(TransportMode.LAN)
    val transportMode: StateFlow<TransportMode> = _transportMode.asStateFlow()

    private val _usbBaseUrl = MutableStateFlow<String?>("ws://127.0.0.1:8765")
    val usbBaseUrl: StateFlow<String?> = _usbBaseUrl.asStateFlow()

    fun setTransportModeFromIntent(modeStr: String?, baseUrl: String?) {
        val newMode = try {
            if (modeStr != null) TransportMode.valueOf(modeStr) else TransportMode.LAN
        } catch (e: Exception) {
            TransportMode.LAN
        }
        
        if (newMode == TransportMode.USB_ADB) {
            if (baseUrl != null && (baseUrl.startsWith("ws://") || baseUrl.startsWith("wss://"))) {
                _usbBaseUrl.value = baseUrl
            } else {
                _usbBaseUrl.value = "ws://127.0.0.1:8765"
            }
        }
        
        if (_transportMode.value != newMode || newMode == TransportMode.USB_ADB) {
            _transportMode.value = newMode
            disconnect()
            
            if (newMode == TransportMode.USB_ADB) {
                _usbBaseUrl.value?.let { connect(it) }
            }
        }
    }

    // Network & Discovery State"""
    
    content = content.replace("    // Network & Discovery State", mode_state)

with open('./app/src/main/java/com/example/ui/MainViewModel.kt', 'w') as f:
    f.write(content)
