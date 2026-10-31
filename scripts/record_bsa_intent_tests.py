"""Record actual native Qt rendering and live tests for the BSA/INTENT milestone.

Run on a desktop with --sources (the verified three CSVs), --archive, --output
(new directory) and --ffmpeg. All interactions are scripted and captioned.
"""

import argparse
import importlib.abc
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("sources", "archive", "output", "ffmpeg"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ["VIRTUALLAB_DATA_DIR"] = str(output / "workspace")

    class NoAI(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, *_):
            if fullname.startswith(("virtual_lab.ai", "google", "groq")):
                raise AssertionError("Unexpected AI provider import")

    sys.meta_path.insert(0, NoAI())

    def deny(*_, **__):
        raise AssertionError("Recording has no network access")

    socket.socket.connect = deny
    socket.socket.bind = deny
    from PySide6.QtCore import Qt, QTimer, QProcess, QProcessEnvironment
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import (
        QApplication,
        QWidget,
        QVBoxLayout,
        QLabel,
        QTabWidget,
        QPlainTextEdit,
        QScrollArea,
        QPushButton,
    )
    from PySide6.QtTest import QTest
    from virtual_lab.pilots.desktop import MSPilotWindow
    from scripts.verify_bsa_workflow import SCANS, URL

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    width, height, fps = 1440, 900, 12
    cast = QWidget()
    cast.setWindowTitle("VirtualLab | BSA and guarded INTENT test recording")
    cast.setFixedSize(width, height)
    layout = QVBoxLayout(cast)
    title = QLabel("VirtualLab | BSA workflow and guarded INTENT tests")
    title.setStyleSheet("font-size:22px;font-weight:bold;padding:8px;color:#126181")
    caption = QLabel(
        "Actual native Qt rendering; scripted controls; live pytest output. No audio."
    )
    caption.setWordWrap(True)
    layout.addWidget(title)
    layout.addWidget(caption)
    tabs = QTabWidget()
    layout.addWidget(tabs, 1)
    window = MSPilotWindow()
    window.setParent(tabs, Qt.Widget)
    tabs.addTab(window, "Actual VirtualLab")
    console = QPlainTextEdit()
    console.setReadOnly(True)
    console.setStyleSheet("font:12px Menlo;background:#101b2b;color:#d6eef9")
    tabs.addTab(console, "Live automated tests")
    footer = QLabel(
        "BSA: THREE SCANS / ONE ACQUISITION | Evidence UNKNOWN | INTENT software fixtures are not laboratory validation | AI / network off"
    )
    footer.setWordWrap(True)
    layout.addWidget(footer)
    cast.show()
    window.show()
    QTest.qWait(600)
    log = (output / "encoder.log").open("wb")
    encoder = subprocess.Popen(
        [
            str(args.ffmpeg),
            "-n",
            "-loglevel",
            "warning",
            "-f",
            "rawvideo",
            "-pixel_format",
            "rgb24",
            "-video_size",
            f"{width}x{height}",
            "-framerate",
            str(fps),
            "-i",
            "-",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output / "VirtualLab-BSA-INTENT-Test-Recording.mp4"),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=log,
    )
    started = time.monotonic()
    frames = 0
    chapters = []

    def capture():
        nonlocal frames
        frame = (
            cast.grab()
            .toImage()
            .scaled(width, height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            .convertToFormat(QImage.Format_RGB888)
        )
        raw = bytes(frame.constBits())
        target = int((time.monotonic() - started) * fps) + 1
        for _ in range(max(1, target - frames)):
            encoder.stdin.write(raw)
            frames += 1

    timer = QTimer()
    timer.timeout.connect(capture)
    timer.start(round(1000 / fps))
    capture()

    def pause(seconds=0.6):
        QTest.qWait(round(seconds * 1000))

    def chapter(name, text):
        title.setText(name)
        caption.setText(text)
        chapters.append(
            {"seconds": round(frames / fps, 2), "title": name, "caption": text}
        )
        print(name, flush=True)
        pause(1.8)

    def click(widget):
        parent = widget.parentWidget()
        while parent:
            if isinstance(parent, QScrollArea):
                parent.ensureWidgetVisible(widget, 12, 15)
            parent = parent.parentWidget()
        pause(0.15)
        QTest.mouseClick(widget, Qt.LeftButton)
        pause()

    def button(root, label):
        found = [b for b in root.findChildren(QPushButton) if b.text() == label]
        assert len(found) == 1, label
        return found[0]

    succeeded = False
    try:
        chapter(
            "1 / Run BSA and INTENT acceptance tests",
            "Live pytest output: signatures, chronology, candidate evaluation/promotion, rollback, cancellation, restart and BSA preservation. Synthetic fixtures are clearly separate from BSA measurements.",
        )
        tabs.setCurrentIndex(1)
        process = QProcess()
        process.setProcessChannelMode(QProcess.MergedChannels)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("QT_QPA_PLATFORM", "offscreen")
        env.insert("VIRTUALLAB_BSA_ZIP", str(args.archive.resolve()))
        process.setProcessEnvironment(env)
        process.setWorkingDirectory(str(Path(__file__).resolve().parents[1]))
        lines = []

        def read_tests():
            text = bytes(process.readAllStandardOutput()).decode(errors="replace")
            lines.append(text)
            console.insertPlainText(text)
            console.ensureCursorVisible()

        process.readyReadStandardOutput.connect(read_tests)
        process.start(
            sys.executable,
            [
                "-m",
                "pytest",
                "tests/intent",
                "tests/pilots/test_bsa_reference.py",
                "tests/gui/test_ms_pilot_workspace.py",
                "-v",
                "--color=no",
                "--junitxml=" + str(output / "recorded-tests.xml"),
            ],
        )
        deadline = time.monotonic() + 60
        while process.state() != QProcess.NotRunning:
            if time.monotonic() > deadline:
                process.kill()
                raise RuntimeError("Recorded tests timed out")
            pause(0.1)
        read_tests()
        (output / "recorded-tests.log").write_text("".join(lines))
        assert process.exitCode() == 0, console.toPlainText()[-4000:]
        pause(3)
        tabs.setCurrentIndex(0)
        chapter(
            "2 / One experiment for one BSA acquisition",
            "All three spectra are preserved in one experiment with a shared sample/acquisition label. Relative scan times are not converted into invented UTC timestamps.",
        )
        service = window.projects.service
        project = service.create_project("BSA public reference: one acquisition")
        service.create_experiment(
            project,
            "BSA1 three spectral scans",
            "Are the submitted peak lists preserved and reproducible?",
        )
        window.tabs.setCurrentIndex(1)
        panel = window.ms_pilot
        results = []
        for name, sha, peaks, seconds in SCANS:
            chapter(
                f"3 / {name} | {peaks} peaks",
                "Scripted form entry and actual workflow buttons. Imported measurements stay UNKNOWN; successful checks establish software integrity only.",
            )
            panel.tabs.setCurrentIndex(0)
            for key, value in {
                "source": str(args.sources.resolve() / name),
                "pilot_id": "bsa-recorded-workflow",
                "dataset_id": Path(name).stem,
                "sample_id": "BSA1-single-acquisition",
                "instrument_id": "claimed-LTQ-Orbitrap-XL",
                "operator_id": "software-workflow-check",
            }.items():
                panel.fields[key].setText(value)
            panel.data_origin.setCurrentIndex(
                panel.data_origin.findData("public_reference")
            )
            panel.source_group.setChecked(True)
            for key, value in {
                "accession": "OpenMS-BSA1/" + Path(name).stem,
                "url": URL,
                "license": "Dataset terms not established; local user-supplied evaluation",
                "attribution": "OpenMS pyOpenMS example; supplied repaired derivative",
                "notes": f"Acquisition group BSA1-single-acquisition. Relative scan time {seconds} seconds; absolute UTC unspecified. No scientific or training approval.",
            }.items():
                panel.source_fields[key].setText(value)
            panel.approval.setChecked(True)
            click(panel.validate_button)
            assert panel.validated is not None, panel.status.text()
            click(panel.import_button)
            assert panel.selected_run is not None, panel.status.text()
            run_id = panel.selected_run
            panel.tabs.setCurrentIndex(1)
            pause(2)
            click(button(panel, "Verify integrity"))
            click(button(panel, "Compare repeat processing"))
            assert "identical" in panel.status.text()
            click(button(panel, "Test alteration detection"))
            assert "PASS" in panel.status.text()
            pause(2)
            results.append(
                {"file": name, "run_id": run_id, "peaks": peaks, "evidence": "UNKNOWN"}
            )
        chapter(
            "4 / INTENT starts off and does not learn from imported MS",
            "No accepted training outcomes or model updates were created by MS import. A workflow approval cannot authorize training.",
        )
        window.tabs.setCurrentIndex(2)
        intent = window.intent_panel
        assert (
            not intent.predictions.isChecked()
            and not intent.learning.isChecked()
            and intent.models.count() == 0
        )
        pause(4)
        chapter(
            "5 / Separate synthetic prediction demonstration",
            "Create a new software-only project and random model. This demonstration commits PREDICTED output, never an experimental observation; no BSA scans are training labels.",
        )
        software = service.create_project("SYNTHETIC software prediction demonstration")
        experiment = service.create_experiment(
            software,
            "Planned fixture",
            "Software control-path test; not a laboratory experiment",
        )
        intent.schema.setPlainText(
            json.dumps(
                {
                    "schema_id": "software-fixture-v1",
                    "description": "Synthetic UI software demonstration only",
                    "features": [
                        {"name": "condition_1", "unit": "fixture units"},
                        {"name": "condition_2", "unit": "fixture units"},
                        {"name": "condition_3", "unit": "fixture units"},
                    ],
                    "outcome_name": "fixture target",
                    "outcome_unit": "fixture units",
                }
            )
        )
        click(button(intent, "Initialize a new model from random weights"))
        intent.conditions.setText(
            '{"condition_1":0.1,"condition_2":0.2,"condition_3":0.3}'
        )
        intent.group.setText("synthetic-software-fixture")
        click(button(intent, "Commit pre-experiment prediction"))
        assert "disabled" in intent.status.text()
        intent.predictions.setChecked(True)
        click(button(intent, "Save INTENT permissions"))
        click(button(intent, "Commit pre-experiment prediction"))
        assert "PREDICTED" in intent.status.text()
        assert not service.store.get_observations_for_experiment(experiment)
        assert not intent.learning.isChecked() and window.workspace.ai_state == "off"
        intent.workspace_scroll.ensureWidgetVisible(intent.status)
        pause(4)
        chapter(
            "Completed / Engineering checks, with scientific limits preserved",
            "Three BSA scans retained as one acquisition, UNKNOWN evidence. Guarded controller tested with synthetic fixtures. Real training still requires institutional reviewer keys and independently measured experimental outcomes.",
        )
        intent.predictions.setChecked(False)
        intent.save_policy()
        cast.grab().save(str(output / "recording-preview.png"))
        pause(4)
        (output / "recording-result.json").write_text(
            json.dumps(
                {
                    "status": "passed",
                    "datasets": results,
                    "synthetic_prediction_created_no_observation": True,
                    "real_training_updates": 0,
                    "assistant": "off",
                    "predictions_final": "off",
                    "learning": "off",
                },
                indent=2,
            )
            + "\n"
        )
        succeeded = True
    finally:
        timer.stop()
        capture()
        encoder.stdin.close()
        encoder.wait(timeout=30)
        log.close()
        (output / "chapters.json").write_text(json.dumps(chapters, indent=2) + "\n")
        (output / "video-provenance.json").write_text(
            json.dumps(
                {
                    "capture": "Actual native Qt widget rendering, not generated app images",
                    "interaction": "Scripted Qt form assignment and QTest mouse events; title captions describe scope",
                    "frames": frames,
                    "fps": fps,
                    "duration_seconds": frames / fps,
                    "tests": "Actual pytest subprocess with log and JUnit",
                    "outcome": "passed" if succeeded else "failed",
                    "network": "blocked",
                    "audio": "none",
                },
                indent=2,
            )
            + "\n"
        )
        window.close()
        cast.close()
        if encoder.returncode:
            raise RuntimeError("Recording encoder failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
