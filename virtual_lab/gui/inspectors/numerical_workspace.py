from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class NumericalWorkspace(QWidget):
    navigateRequested = Signal(str)

    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Numerical verification • scope is limited to the reported comparison"))

        # Compact metric summary grid
        self.summary_card = QGroupBox("NUMERICAL CERTIFICATE SUMMARY")
        grid = QGridLayout(self.summary_card)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self.lbl_status = QLabel("NOT RUN")
        self.lbl_envelope = QLabel("—")
        self.lbl_reference = QLabel("—")
        self.lbl_execution = QLabel("—")
        self.lbl_abs_err = QLabel("—")
        self.lbl_scaled_err = QLabel("—")
        self.lbl_tolerances = QLabel("—")
        self.lbl_scope = QLabel("—")
        self.lbl_cert_id = QLabel("—")

        pairs = [
            ("Status", self.lbl_status, "Envelope", self.lbl_envelope),
            ("Reference", self.lbl_reference, "Execution", self.lbl_execution),
            ("Max absolute error", self.lbl_abs_err, "Max scaled error", self.lbl_scaled_err),
            ("Tolerances (atol / rtol)", self.lbl_tolerances, "Certificate ID", self.lbl_cert_id),
        ]
        for row_idx, (l1, w1, l2, w2) in enumerate(pairs):
            k1 = QLabel(f"{l1}:")
            k1.setStyleSheet("color: #8b9bb4;")
            k2 = QLabel(f"{l2}:")
            k2.setStyleSheet("color: #8b9bb4;")
            for val_lbl in (w1, w2):
                val_lbl.setTextFormat(Qt.PlainText)
                val_lbl.setWordWrap(True)
            grid.addWidget(k1, row_idx, 0)
            grid.addWidget(w1, row_idx, 1)
            grid.addWidget(k2, row_idx, 2)
            grid.addWidget(w2, row_idx, 3)

        scope_key = QLabel("Scope:")
        scope_key.setStyleSheet("color: #8b9bb4;")
        self.lbl_scope.setTextFormat(Qt.PlainText)
        self.lbl_scope.setWordWrap(True)
        grid.addWidget(scope_key, len(pairs), 0)
        grid.addWidget(self.lbl_scope, len(pairs), 1, 1, 3)
        layout.addWidget(self.summary_card)

        # Compact raw certificate inspector (preserved for backward compatibility & copyable record)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(190)
        self.details.setPlainText("NOT RUN — no numerical certificate exists.")
        layout.addWidget(self.details)

        # Next-step pipeline actions
        actions_frame = QFrame()
        actions_layout = QHBoxLayout(actions_frame)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        self.next_hint = QLabel("Next pipeline step: compare simulation runs, inspect curated literature evidence, or record your conclusion.")
        self.next_hint.setWordWrap(True)
        actions_layout.addWidget(self.next_hint, 1)

        self.btn_compare = QPushButton("Compare Results")
        self.btn_compare.clicked.connect(lambda: self.navigateRequested.emit("Compare"))
        self.btn_evidence = QPushButton("Review Evidence")
        self.btn_evidence.clicked.connect(lambda: self.navigateRequested.emit("Evidence"))
        self.btn_conclusion = QPushButton("Record Conclusion")
        self.btn_conclusion.setObjectName("primary")
        self.btn_conclusion.clicked.connect(lambda: self.navigateRequested.emit("Conclusion"))
        for btn in (self.btn_compare, self.btn_evidence, self.btn_conclusion):
            actions_layout.addWidget(btn)
        layout.addWidget(actions_frame)
        layout.addStretch()

        workspace.resultChanged.connect(self.update_result)

    def update_result(self, r):
        if r is None:
            self.lbl_status.setText("NOT RUN")
            self.lbl_status.setStyleSheet("")
            for lbl in (
                self.lbl_envelope,
                self.lbl_reference,
                self.lbl_execution,
                self.lbl_abs_err,
                self.lbl_scaled_err,
                self.lbl_tolerances,
                self.lbl_scope,
                self.lbl_cert_id,
            ):
                lbl.setText("—")
            self.details.setPlainText("Select a saved simulation in Projects to view its numerical check.")
            return
        nc = r.numerical_check
        status = nc.get('status', 'FAILED')
        env = "WITHIN RANGE" if status == "PASSED" else "OUTSIDE CERTIFIED ENVELOPE"
        ref = nc.get('reference', 'Unknown')
        exec_meta = r.execution_metadata.get('numpy_version', 'MLX / Metal FP32')
        abs_err = nc.get('max_absolute_error', 'N/A')
        scaled_err = nc.get('max_scaled_error', 'N/A')
        abs_err_str = f"{abs_err:.2e}" if isinstance(abs_err, (int, float)) else str(abs_err)
        scaled_err_str = f"{scaled_err:.2e}" if isinstance(scaled_err, (int, float)) else str(scaled_err)
        atol = nc.get('atol', 'N/A')
        rtol = nc.get('rtol', 'N/A')
        scope = nc.get('scope', 'Unknown')

        self.lbl_status.setText(status)
        self.lbl_status.setStyleSheet(
            "color: #22c55e; font-weight: bold;" if status == "PASSED" else "color: #ef4444; font-weight: bold;"
        )
        self.lbl_envelope.setText(env)
        self.lbl_reference.setText(str(ref))
        self.lbl_execution.setText(str(exec_meta))
        self.lbl_abs_err.setText(abs_err_str)
        self.lbl_scaled_err.setText(scaled_err_str)
        self.lbl_tolerances.setText(f"atol={atol}, rtol={rtol}")
        self.lbl_scope.setText(f"{scope} (numerical solver agreement only; not biological validation)")
        self.lbl_cert_id.setText(str(r.run_id))

        cert = f"""NUMERICAL CERTIFICATE

Status                 {status}
Envelope               {env}

Reference
{ref}

Execution
{exec_meta}

A ↔ C
max absolute error     {abs_err_str}
max scaled error       {scaled_err_str}

Tolerance
atol                   {atol}
rtol                   {rtol}

Scope
{scope}

Certificate ID
{r.run_id}
"""
        self.details.setPlainText(cert)

