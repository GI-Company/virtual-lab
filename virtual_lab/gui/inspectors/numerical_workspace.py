import json
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QPlainTextEdit
class NumericalWorkspace(QWidget):
    def __init__(self,workspace,parent=None):
        super().__init__(parent);layout=QVBoxLayout(self)
        layout.addWidget(QLabel("Numerical verification • scope is limited to the reported comparison"))
        self.details=QPlainTextEdit();self.details.setReadOnly(True);self.details.setPlainText("NOT RUN — no numerical certificate exists.")
        layout.addWidget(self.details);workspace.resultChanged.connect(self.update_result)
    def update_result(self,r):
        nc = r.numerical_check
        status = nc.get('status', 'FAILED')
        env = "WITHIN RANGE" if status == "PASSED" else "OUTSIDE CERTIFIED ENVELOPE"
        ref = nc.get('reference', 'Unknown')
        
        cert = f"""NUMERICAL CERTIFICATE

Status                 {status}
Envelope               {env}

Reference
{ref}

Execution
{r.execution_metadata.get('numpy_version', 'MLX / Metal FP32')}

A ↔ C
max absolute error     {nc.get('max_absolute_error', 'N/A'):.2e}
max scaled error       {nc.get('max_scaled_error', 'N/A'):.2e}

Tolerance
atol                   {nc.get('atol', 'N/A')}
rtol                   {nc.get('rtol', 'N/A')}

Scope
{nc.get('scope', 'Unknown')}

Certificate ID
{r.run_id}
"""
        self.details.setPlainText(cert)
