import re

with open('./app/src/main/java/com/example/MainActivity.kt', 'r') as f:
    content = f.read()

new_content = """package com.example

import android.content.Intent
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import com.example.ui.MainViewModel
import com.example.ui.SensorNodeApp
import com.example.ui.theme.MyApplicationTheme

class MainActivity : ComponentActivity() {
    private val viewModel: MainViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        handleIntent(intent)
        setContent {
            MyApplicationTheme {
                SensorNodeApp(viewModel = viewModel)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent?) {
        if (intent == null) return
        val transportMode = intent.getStringExtra("VIRTUAL_LAB_TRANSPORT_MODE")
        val baseUrl = intent.getStringExtra("VIRTUAL_LAB_BASE_URL")
        
        if (transportMode != null) {
            Log.d("MainActivity", "Received Intent Transport Mode: $transportMode, Base URL: $baseUrl")
            viewModel.setTransportModeFromIntent(transportMode, baseUrl)
        }
    }
}
"""

with open('./app/src/main/java/com/example/MainActivity.kt', 'w') as f:
    f.write(new_content)
