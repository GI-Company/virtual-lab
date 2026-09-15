from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from PySide6.QtCore import Qt

from virtual_lab.ai.credentials import CredentialService
from virtual_lab.ai.providers.gemini import GeminiProvider

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Provider")
        self.setMinimumWidth(400)
        
        self.credential_service = CredentialService()
        self.provider = GeminiProvider()
        
        layout = QVBoxLayout(self)
        
        lbl_title = QLabel("GEMINI")
        lbl_title.setStyleSheet("font-weight: bold; color: #8b9bb4;")
        layout.addWidget(lbl_title)
        
        self.lbl_status = QLabel()
        self._update_status_label()
        layout.addWidget(self.lbl_status)
        
        layout.addSpacing(15)
        layout.addWidget(QLabel("API Key"))
        
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        # We purposely do not load the actual key into the UI, just show a placeholder if it's configured
        if self.provider.is_configured():
            self.api_key_input.setPlaceholderText("••••••••••••••••••••••••••")
        layout.addWidget(self.api_key_input)
        
        layout.addSpacing(15)
        
        actions = QHBoxLayout()
        self.btn_remove = QPushButton("Remove Credential")
        self.btn_remove.clicked.connect(self._remove_credential)
        if not self.provider.is_configured():
            self.btn_remove.setEnabled(False)
            
        self.btn_save_test = QPushButton("Save & Test")
        self.btn_save_test.setObjectName("primary")
        self.btn_save_test.clicked.connect(self._save_and_test)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        
        actions.addWidget(self.btn_remove)
        actions.addStretch()
        actions.addWidget(self.btn_cancel)
        actions.addWidget(self.btn_save_test)
        
        layout.addLayout(actions)
        
    def _update_status_label(self):
        if self.provider.is_configured():
            self.lbl_status.setText("Status: <span style='color: #22c55e; font-weight: bold;'>AVAILABLE</span>")
        else:
            self.lbl_status.setText("Status: <span style='color: #ef4444; font-weight: bold;'>NOT CONFIGURED</span>")

    def _remove_credential(self):
        self.credential_service.remove_api_key("gemini")
        self.provider = GeminiProvider() # Re-init
        self.api_key_input.clear()
        self.api_key_input.setPlaceholderText("")
        self.btn_remove.setEnabled(False)
        self._update_status_label()
        
    def _save_and_test(self):
        new_key = self.api_key_input.text().strip()
        if not new_key:
            QMessageBox.warning(self, "Invalid Key", "Please enter a valid API key.")
            return
            
        self.btn_save_test.setText("Testing...")
        self.btn_save_test.setEnabled(False)
        self.api_key_input.setEnabled(False)
        
        # Test connection before saving
        try:
            self.provider.test_connection(override_key=new_key)
            # If successful, save it
            self.credential_service.set_api_key("gemini", new_key)
            QMessageBox.information(self, "Success", "Gemini API key is valid and has been securely stored.")
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Connection Failed", f"Failed to verify API key:\n\n{exc}")
            self.btn_save_test.setText("Save & Test")
            self.btn_save_test.setEnabled(True)
            self.api_key_input.setEnabled(True)
