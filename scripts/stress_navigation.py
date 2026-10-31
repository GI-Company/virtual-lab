"""Bounded offline Qt navigation/GC stress, using actual simulation workers.

Run from the checkout with a NEW --output directory. QT_QPA_PLATFORM controls
native versus offscreen rendering; no platform override is made by this driver.
The existing application's default GC timer/thresholds are retained. This is a
software stress test with synthetic results, not laboratory or OS certification.
"""

from __future__ import annotations

import argparse
import gc
import importlib.abc
import json
import os
from pathlib import Path
import platform
import socket
import sys
import threading
import time
import traceback

REPO = Path(__file__).resolve().parents[1]


def bounded_int(minimum, maximum):
    def parse(value):
        number = int(value)
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f"Expected {minimum}..{maximum}")
        return number

    return parse


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cycles", type=bounded_int(1, 200), default=20)
    parser.add_argument("--dwell-ms", type=bounded_int(1100, 5000), default=1250)
    parser.add_argument("--timeout-seconds", type=bounded_int(5, 120), default=25)
    args = parser.parse_args(argv)
    if not __debug__:
        parser.error("Stress verification requires Python assertions to be enabled")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ["VIRTUALLAB_DATA_DIR"] = str(output / "workspace")
    os.environ.pop("VIRTUALLAB_RUN_LIVE_AI_TESTS", None)
    sys.path.insert(0, str(REPO))
    started = time.monotonic()
    gui_thread = threading.get_ident()
    original_gc_enabled = gc.isenabled()
    events_path = output / "events.jsonl"
    completed = []
    collections = []
    violations = []
    python_network_attempts = []
    keyring_attempts = []
    blocked_viewer_requests = []
    allocator_threads = set()
    simulation_threads = set()
    allocation_active = threading.Event()
    simulation_active = threading.Event()
    state = {"cycle": -1, "stage": "startup"}

    def log(kind, **values):
        event = {
            "elapsed_seconds": round(time.monotonic() - started, 4),
            "cycle": state["cycle"],
            "stage": state["stage"],
            "kind": kind,
            **values,
        }
        with events_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, allow_nan=False) + "\n")
        if kind in ("cycle_completed", "failed", "completed"):
            print(json.dumps(event, allow_nan=False), flush=True)

    class NoAI(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, *unused):
            if fullname == "virtual_lab.ai" or fullname.startswith(
                (
                    "virtual_lab.ai.",
                    "google.adk",
                    "google.genai",
                    "mlx_lm",
                    "openai",
                    "groq",
                    "anthropic",
                    "ollama",
                )
            ):
                violations.append("AI import: " + fullname)
                raise ImportError(
                    "AI is unavailable during offline stress: " + fullname
                )

    blocker = NoAI()
    sys.meta_path.insert(0, blocker)
    original_connect, original_bind = socket.socket.connect, socket.socket.bind

    def deny_network(*unused, **unused_kwargs):
        python_network_attempts.append(state.copy())
        raise RuntimeError("Python network access is blocked in offline stress")

    socket.socket.connect = deny_network
    socket.socket.bind = deny_network

    import keyring

    original_keyring = {
        name: getattr(keyring, name)
        for name in ("get_password", "set_password", "delete_password")
    }

    def deny_keyring(*unused, **unused_kwargs):
        keyring_attempts.append(state.copy())
        raise RuntimeError("OS credential access is blocked in offline stress")

    for name in original_keyring:
        setattr(keyring, name, deny_keyring)

    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import (
        QCoreApplication,
        QEvent,
        QRunnable,
        QThreadPool,
        QtMsgType,
        qInstallMessageHandler,
        qVersion,
    )
    from PySide6.QtWidgets import QApplication
    import shiboken6
    from virtual_lab.gui.shell.gui_gc import ensure_gui_gc
    from virtual_lab.gui.services.experiment_controller import SimulationWorker
    from virtual_lab.gui.shell.main_window import VirtualLabApplication

    original_excepthook = sys.excepthook

    def exception_hook(exc_type, exc_value, exc_tb):
        detail = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        violations.append("Unhandled Qt/Python callback: " + detail)
        log("python_callback_error", detail=detail)

    sys.excepthook = exception_hook

    def qt_message(level, context, message):
        expected_denial = "Uncaught (in promise) TypeError: Failed to fetch: Network egress is strictly DISABLED in Local Research Mode."
        if message == expected_denial:
            blocked_viewer_requests.append(
                {"cycle": state["cycle"], "message": message}
            )
            log("viewer_fetch_denied", level=str(level), message=message)
            return
        if level in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg) or any(
            text in message
            for text in (
                "Timers cannot be",
                "Cannot create children for a parent",
                "QThread: Destroyed",
                "QObject::moveToThread",
                "QObject::startTimer",
                "QObject::killTimer",
            )
        ):
            violations.append("Qt error: " + message)
        log("qt_message", level=str(level), message=message[:2000])

    previous_qt_handler = qInstallMessageHandler(qt_message)
    original_run = SimulationWorker.run

    def observed_run(worker):
        simulation_threads.add(threading.get_ident())
        simulation_active.set()
        try:
            return original_run(worker)
        finally:
            simulation_active.clear()

    SimulationWorker.run = observed_run

    def collection(phase, info):
        if phase != "start":
            return
        thread = threading.get_ident()
        item = {
            "thread": thread,
            "generation": info.get("generation"),
            "cycle": state["cycle"],
            "stage": state["stage"],
            "allocation_active": allocation_active.is_set(),
            "simulation_active": simulation_active.is_set(),
        }
        collections.append(item)
        if thread != gui_thread:
            violations.append("Collection outside GUI thread")

    gc.callbacks.append(collection)

    class CycleAllocator(QRunnable):
        def __init__(self, seconds):
            super().__init__()
            self.seconds = seconds
            self.done = threading.Event()
            self.error = None
            self.count = 0

        def run(self):
            allocator_threads.add(threading.get_ident())
            allocation_active.set()
            try:
                deadline = time.monotonic() + self.seconds
                while time.monotonic() < deadline:
                    for unused in range(128):
                        item = []
                        item.append({"owner": item})
                        self.count += 1
                    time.sleep(0.005)
            except BaseException:
                self.error = traceback.format_exc()
            finally:
                allocation_active.clear()
                self.done.set()

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("VirtualLab offline navigation stress")
    actual_qt_platform = app.platformName()
    guard = ensure_gui_gc()
    threshold = guard.threshold
    interval_ms = guard.timer.interval()
    assert guard.timer.parent() is app and interval_ms == 1000
    assert not gc.isenabled()
    window = None
    outcome = "failed"
    failure = None
    total_allocations = 0
    guard_blocks = 0
    known_results = {}

    def pump_until(condition, description, minimum_seconds=0):
        began = time.monotonic()
        deadline = began + args.timeout_seconds
        while not condition() or time.monotonic() - began < minimum_seconds:
            app.processEvents()
            if violations:
                raise AssertionError(violations[-1])
            if time.monotonic() > deadline:
                raise TimeoutError(description)
            time.sleep(0.003)
        app.processEvents()
        if violations:
            raise AssertionError(violations[-1])

    def assert_inactive(current):
        assert current.runtime.agent_runtime is None and current.local_research is None
        assert not current.runtime.gateway.server.isListening()
        assert current.workspace.ai_state == "off"
        policy = current.intent_panel.controller.policy()
        assert not policy.predictions_enabled and not policy.learning_enabled
        assert not list(
            current.ledger.conn.execute(
                "SELECT 1 FROM ledger_events WHERE event_type IN ('INTENT_PREDICTION_COMMITTED','INTENT_MODEL_UPDATED')"
            )
        )

    def close_current():
        nonlocal window
        if window is None:
            return
        assert window.experiment.controller.worker is None
        assert QThreadPool.globalInstance().waitForDone(5000)
        window.close()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        window = None

    try:
        log(
            "started",
            cycles=args.cycles,
            dwell_ms=args.dwell_ms,
            python=sys.version,
            qt=qVersion(),
            pyside=pyside_version,
            platform=platform.platform(),
            qt_platform=app.platformName(),
            gc_timer_interval_ms=interval_ms,
            gc_thresholds=list(threshold),
        )
        window = VirtualLabApplication()
        window.show()
        study = window.projects.service
        projects = [
            study.create_project("Synthetic stress " + name, "physics_simulation")
            for name in ("Alpha", "Beta")
        ]
        assert_inactive(window)
        for index in range(args.cycles):
            state.update(cycle=index, stage="open_project")
            nav = window.navigation
            project = projects[index % 2]
            nav.open_project(project)
            study = window.projects.service
            experiment = study.create_experiment(
                project,
                f"Synthetic cycle {index+1}",
                "Software stability and scope test; no laboratory evidence",
            )
            controller = window.experiment.controller
            errors = []
            controller.runFailed.connect(errors.append)
            before = len(collections)
            allocator = CycleAllocator(args.dwell_ms / 1000)
            QThreadPool.globalInstance().start(allocator)
            state["stage"] = "workers_active"
            controller.run_experiment(
                dict(
                    model_id="gene_expression",
                    duration_h=1,
                    members=4,
                    concentration_um=float(index % 6),
                    seed=42 + index,
                )
            )
            assert controller.worker is not None
            try:
                nav.show_home()
            except ValueError:
                guard_blocks += 1
            else:
                raise AssertionError(
                    "Navigation left a project while a worker was pending"
                )
            assert window.workspace.active_project_id == project
            pump_until(
                lambda: controller.worker is None and allocator.done.is_set(),
                "Simulation/allocation did not finish",
                minimum_seconds=args.dwell_ms / 1000,
            )
            assert QThreadPool.globalInstance().waitForDone(5000)
            assert not errors and allocator.error is None
            assert (
                guard.threshold == threshold and guard.timer.interval() == interval_ms
            )
            assert not gc.isenabled()
            total_allocations += allocator.count
            observations = study.store.get_observations_for_experiment(experiment)
            assert len(observations) == 1
            observation = observations[0]
            result = study.inspect(observation)
            assert observation.epistemic_state.value == "SIMULATED"
            assert (
                result["id"] == observation.session_id
                and result["experiment_id"] == experiment
            )
            assert window.workspace.current_result.run_id == observation.session_id
            known_results[experiment] = (
                observation.session_id,
                observation.artifact_sha256,
            )
            window.projects.refresh_results()
            window.projects.results.setCurrentRow(0)
            nav.open_tool("analysis")
            assert window.analysis.result.run_id == observation.session_id
            other = projects[(index + 1) % 2]
            state["stage"] = "switch_project"
            nav.open_project(other)
            assert window.workspace.active_project_id == other
            assert all(
                obs.experiment_id != experiment
                for obs, label in window.compare.runs.values()
            )
            assert all(
                event["payload"].get("experiment_id") != experiment
                and event["payload"].get("run_id") != observation.session_id
                for event in window.provenance.events
            )
            nav.open_project(project)
            assert window.workspace.active_experiment.id == experiment
            assert window.tabs.currentWidget() is window.analysis
            assert window.analysis.result.run_id == observation.session_id
            assert_inactive(window)
            window.ledger.verify_chain()
            state["stage"] = "reopen_window"
            close_current()
            window = VirtualLabApplication()
            window.show()
            pump_until(
                lambda: window.workspace.active_experiment is not None,
                "Project did not restore",
            )
            assert window.workspace.active_project_id == project
            assert window.workspace.active_experiment.id == experiment
            assert window.tabs.currentWidget() is window.analysis
            assert window.analysis.result.run_id == observation.session_id
            restored = window.projects.service.store.get_observations_for_experiment(
                experiment
            )
            assert (
                len(restored) == 1
                and restored[0].artifact_sha256 == observation.artifact_sha256
            )
            window.projects.service.inspect(restored[0])
            assert_inactive(window)
            window.navigation.open_tool("instruments")
            assert not window.runtime.gateway.server.isListening()
            window.navigation.open_tool("analysis")
            record = {
                "cycle": index + 1,
                "project_id": project,
                "experiment_id": experiment,
                "run_id": observation.session_id,
                "artifact_sha256": observation.artifact_sha256,
                "cyclic_allocations": allocator.count,
                "collections": len(collections) - before,
                "collection_during_allocation": any(
                    c["allocation_active"] for c in collections[before:]
                ),
                "status": "passed",
            }
            assert record["collections"] > 0, "The default GC timer was not exercised"
            completed.append(record)
            log("cycle_completed", **record)
        state["stage"] = "final_teardown"
        for experiment, (run_id, sha256) in known_results.items():
            observations = (
                window.projects.service.store.get_observations_for_experiment(
                    experiment
                )
            )
            assert len(observations) == 1
            assert (
                observations[0].session_id == run_id
                and observations[0].artifact_sha256 == sha256
            )
            window.projects.service.inspect(observations[0])
        close_current()
        assert guard.timer.isActive() and guard.timer.parent() is app
        assert QThreadPool.globalInstance().waitForDone(5000)
        assert not python_network_attempts and not keyring_attempts
        assert collections and all(c["thread"] == gui_thread for c in collections)
        assert any(c["allocation_active"] for c in collections)
        assert simulation_threads and all(t != gui_thread for t in simulation_threads)
        assert allocator_threads and all(t != gui_thread for t in allocator_threads)
        # Explicitly end this single QApplication only after all windows/workers are
        # gone, so its GC-policy restoration path is verified rather than assumed.
        shiboken6.delete(app)
        assert gc.isenabled() == original_gc_enabled
        assert not violations
        outcome = "passed"
        log(
            "completed",
            iterations=len(completed),
            cyclic_allocations=total_allocations,
            collections=len(collections),
            gc_policy_restored=gc.isenabled(),
        )
    except BaseException:
        failure = traceback.format_exc()
        log("failed", detail=failure)
        try:
            if shiboken6.isValid(app):
                if window is not None and shiboken6.isValid(window):
                    controller = window.experiment.controller
                    if controller.worker is not None:
                        controller.cancel()
                    cleanup_deadline = time.monotonic() + 5
                    while (
                        controller.worker is not None
                        and time.monotonic() < cleanup_deadline
                    ):
                        app.processEvents()
                        time.sleep(0.003)
                    assert (
                        controller.worker is None
                    ), "Worker did not cancel during failed-run cleanup"
                assert QThreadPool.globalInstance().waitForDone(6000)
                close_current()
                shiboken6.delete(app)
        except BaseException:
            violations.append("Failed-run cleanup: " + traceback.format_exc())
    finally:
        gc.callbacks.remove(collection)
        SimulationWorker.run = original_run
        qInstallMessageHandler(previous_qt_handler)
        sys.excepthook = original_excepthook
        socket.socket.connect, socket.socket.bind = original_connect, original_bind
        for name, function in original_keyring.items():
            setattr(keyring, name, function)
        sys.meta_path.remove(blocker)
        summary = {
            "format": "virtuallab-navigation-stress-v1",
            "status": outcome,
            "requested_cycles": args.cycles,
            "completed_cycles": len(completed),
            "dwell_ms": args.dwell_ms,
            "elapsed_seconds": round(time.monotonic() - started, 4),
            "python": sys.version,
            "qt": qVersion(),
            "pyside": pyside_version,
            "platform": platform.platform(),
            "qt_platform": actual_qt_platform,
            "requested_qt_platform": os.environ.get(
                "QT_QPA_PLATFORM", "native default"
            ),
            "gui_thread": gui_thread,
            "simulation_threads": sorted(simulation_threads),
            "allocator_threads": sorted(allocator_threads),
            "cyclic_allocations": total_allocations,
            "default_gc_interval_ms": interval_ms,
            "gc_thresholds": list(threshold),
            "gc_collections": collections,
            "collection_thread_ids": sorted({c["thread"] for c in collections}),
            "navigation_guards_blocked": guard_blocks,
            "python_network_attempts": len(python_network_attempts),
            "credential_store_attempts": len(keyring_attempts),
            "violations": violations,
            "blocked_viewer_requests": blocked_viewer_requests,
            "gc_policy_restored": gc.isenabled() == original_gc_enabled,
            "iterations": completed,
            "failure": failure,
            "scope": "Synthetic software stress; no laboratory data, provider activation or scientific validation. RHO rendering is not validated; exact existing intentional nonlocal viewer-fetch denials are retained separately.",
        }
        (output / "result.json").write_text(
            json.dumps(summary, indent=2, allow_nan=False) + "\n"
        )
    return 0 if outcome == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
