"""Regression tests for the 2026-10 codebase audit remediations (C-1..C-12, H-1..H-14, M-1..M-12)."""
import hashlib
import json
import os
import struct
import zipfile
from pathlib import Path

import numpy as np
import pytest

from virtual_lab.core.canonical import canonical_json
from virtual_lab.core.ledger import Actor, GenesisLedger
from virtual_lab.core.provenance_export import verify_genesis_chain
from virtual_lab.core.trusted_signers import get_signer_status
from virtual_lab.core.vlprogram_importer import VLProgramError, load_vlprogram
from virtual_lab.domain.approval_policy import (
    ApprovalPolicy,
    Proposal,
)
from virtual_lab.domain.epistemics import EpistemicState
from virtual_lab.domain.observation import PhysicalDimension, units_are_convertible


def test_c1_ledger_persists_actor_provider_and_model_and_verifies_export(tmp_path):
    """C-1: GenesisLedger persists Actor(provider, model) and verify_genesis_chain succeeds."""
    db_path = str(tmp_path / "genesis.db")
    ledger = GenesisLedger(db_path)
    try:
        actor = Actor(type="AI", id="agent-1", provider="Google", model="gemini-2.5-flash")
        ledger.append("evt-ai-1", actor, "PROPOSAL_CREATED", {"val": -0.0})
        ledger.verify_chain()
    finally:
        ledger.conn.close()

    events, dag_errors = verify_genesis_chain(db_path)
    assert len(events) == 2
    assert dag_errors == []
    assert events[1]["actor"]["provider"] == "Google"
    assert events[1]["actor"]["model"] == "gemini-2.5-flash"


def test_canonical_json_normalizes_negative_zero():
    """M-4 / C-1: -0.0 and 0.0 serialize identically under canonical_json."""
    assert canonical_json({"a": -0.0, "b": [-0.0]}) == canonical_json({"a": 0.0, "b": [0.0]})


def test_c2_run_store_unifies_with_genesis_db(tmp_path, monkeypatch):
    """C-2: RunStore writes to genesis.db by default and reads legacy ledger.db when present."""
    from virtual_lab.gui.services.run_store import RunStore

    monkeypatch.setenv("VIRTUALLAB_DATA_DIR", str(tmp_path))
    store = RunStore(tmp_path)
    run_payload = {"id": "run-123", "value": 42}
    store.save(run_payload)
    assert (tmp_path / "genesis.db").exists()
    assert store.load_all() == [run_payload]


def test_c3_vlprogram_importer_unpacks_signer_tuple_and_rejects_traversal(tmp_path):
    """C-3: get_signer_status tuple unpacking and path traversal protection in load_vlprogram."""
    from nacl.signing import SigningKey
    from virtual_lab.core.trusted_signers import _REGISTRY, SignerRole, TrustedSigner, TrustState

    sk = SigningKey.generate()
    pk_hex = sk.verify_key.encode().hex()

    manifest = {
        "program_id": "test_prog",
        "version": "1.0.0",
        "artifacts": {"../escape.txt": "0" * 64},
    }
    manifest_bytes = canonical_json(manifest)
    manifest_hash = hashlib.sha256(manifest_bytes).digest()
    sig_hex = sk.sign(manifest_hash).signature.hex()

    manifest["vlprogram_signature"] = sig_hex
    manifest["vlprogram_public_key"] = pk_hex
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    _REGISTRY[pk_hex] = TrustedSigner(
        signer_id="test-dev",
        public_key_hex=pk_hex,
        fingerprint="sha256:test",
        status=TrustState.TRUSTED,
        permitted_roles=[SignerRole.PROGRAM_SIGNER],
        added_at="2025-01-01T00:00:00Z",
    )
    try:
        with pytest.raises(VLProgramError, match="Invalid artifact path"):
            load_vlprogram(str(tmp_path))
    finally:
        _REGISTRY.pop(pk_hex, None)


def test_c5_sensornode_provider_list_devices_uses_valid_instrument_states():
    """C-5: SensorNodeProvider.list_devices() does not raise AttributeError on InstrumentState."""
    from virtual_lab.gateway.providers.sensornode import SensorNodeProvider
    from virtual_lab.instruments.connection import (
        ChannelConnectionState,
        ConnectionRegistry,
        SensorChannelState,
    )

    registry = ConnectionRegistry()
    conn = ChannelConnectionState(
        channel_type="sensors",
        connection_id="CONN-1",
        generation=1,
        socket=None,
        remote_address="127.0.0.1",
        connected_utc=1000,
        state=SensorChannelState.STREAMING,
    )
    registry.add_connection(conn)
    registry.bind_connection("CONN-1", "DEV-1")

    provider = SensorNodeProvider(registry=registry)
    devices = provider.list_devices()
    assert any(d["device_id"] == "DEV-1" and d["connection_state"] == "ONLINE" for d in devices)


def test_c7_approval_policy_iso_timestamp_and_replay_protection(tmp_path):
    """C-7: ApprovalPolicy parses ISO timestamps with +00:00 vs Z and blocks proposal replay."""
    from nacl.signing import SigningKey
    from virtual_lab.core.trusted_signers import _REGISTRY, SignerRole, TrustedSigner, TrustState

    sk = SigningKey.generate()
    pk_bytes = sk.verify_key.encode()
    pk_hex = pk_bytes.hex()
    _REGISTRY[pk_hex] = TrustedSigner(
        signer_id="op-1",
        public_key_hex=pk_hex,
        fingerprint="sha256:op1",
        status=TrustState.TRUSTED,
        permitted_roles=[SignerRole.HUMAN_APPROVAL],
        added_at="2025-01-01T00:00:00Z",
    )

    ledger = GenesisLedger(str(tmp_path / "genesis.db"))
    try:
        proposal = Proposal(
            proposal_id="prop-1",
            action_type="RUN_SIMULATION",
            parameters={"dt": 0.1},
            target="exp-1",
            actor_id="op-1",
            issued_at="2026-01-01T00:00:00Z",
            expires_at="2099-01-01T00:00:00+00:00",
            nonce="nonce-1",
        )
        policy = ApprovalPolicy(genesis_ledger=ledger)
        sig = policy.sign_proposal(proposal, sk)

        ledger.append(
            "prop-evt-1",
            Actor(type="AI", id="agent-1"),
            "AI_PROPOSAL",
            {
                **__import__("dataclasses").asdict(proposal),
                "action_type": "RUN_SIMULATION",
                "target": "exp-1",
                "parameters": {"dt": 0.1},
            },
        )
        ledger.append(
            "rule-evt-1",
            Actor(type="SYSTEM", id="rules-1"),
            "RULE_EVALUATION",
            {
                "proposal_id": "prop-1",
                "passed": True,
            },
        )
        ledger.append(
            "dec-1",
            Actor(type="HUMAN", id="op-1"),
            "HUMAN_DECISION",
            {
                "proposal_id": "prop-1",
                "decision": "APPROVED",
                "signature": sig.hex(),
            },
        )
        assert policy.verify_and_execute(proposal, sig, pk_bytes, lambda p: "OK", human_actor_id="op-1") == "OK"
        # Second execution of the same proposal/nonce must be rejected as replay
        with pytest.raises(ValueError, match="PROPOSAL_ALREADY_EXECUTED"):
            policy.verify_and_execute(proposal, sig, pk_bytes, lambda p: "OK", human_actor_id="op-1")
    finally:
        ledger.conn.close()
        _REGISTRY.pop(pk_hex, None)


def test_c10_agent_genesis_recorder_multiple_retrievals_do_not_collide():
    """C-10: Multiple memory/evidence retrieval events in one episode get distinct event IDs."""
    from virtual_lab.ai.agent.genesis_adapter import AgentGenesisRecorder

    recorder = AgentGenesisRecorder()
    h1 = recorder.record_memory_retrieved("ep1", ["refA"])
    h2 = recorder.record_memory_retrieved("ep1", ["refB"])
    e1 = recorder.record_evidence_retrieved("ep1", ["ev1"])
    e2 = recorder.record_evidence_retrieved("ep1", ["ev2"])
    assert len({h1, h2, e1, e2}) == 4


def test_c12_calibration_workspace_supports_local_metadata_transfer(qtbot, tmp_path, monkeypatch):
    """C-12: Local CSV calibration with declared gene/organism/condition transfers to BiologicalSystem."""
    from tests.calibration.test_decay import make_service
    from virtual_lab.biology.calibration_bridge import system_from_calibration
    from virtual_lab.calibration.decay import DATA
    from virtual_lab.gui.calibration_workspace import CalibrationWorkspace

    svc = make_service(tmp_path / "cal_transfer", monkeypatch)
    svc.create_experiment(svc.create_project("Decay"), "LocalTransfer", "Can local CSV transfer?")
    panel = CalibrationWorkspace(svc.workspace, svc)
    qtbot.addWidget(panel)
    panel.mode.setCurrentIndex(1)
    panel.path.setText(str(DATA / "pgk1_decay.csv"))
    panel.context.setText("Yeast PGK1 shutoff")
    panel.gene.setText("PGK1")
    panel.organism.setText("Saccharomyces cerevisiae")
    panel.condition.setText("Glucose shutoff")
    panel.source.setText("Local benchmark CSV")
    panel.scale.setCurrentIndex(1)
    panel._fit()
    assert panel.result is not None
    panel._save()
    obs = svc.store.get_observations_for_experiment(svc.workspace.active_experiment.id)[0]
    system = system_from_calibration(svc.inspect(obs))
    assert system.objects[0].identity.label == "PGK1"


def test_h1_h2_biological_epistemic_state_unification_and_rho_parameters():
    """H-1 & H-2: biological.parameters.EpistemicState is domain.epistemics.EpistemicState and RHO parameters are MODEL_ASSUMPTION."""
    from virtual_lab.biological.parameters import EpistemicState as BioEpistemicState
    from virtual_lab.diseases.rho_p23h.parameters import RHO_P23H_PARAMETERS

    assert BioEpistemicState is EpistemicState
    assert all(p.epistemic_state == EpistemicState.MODEL_ASSUMPTION for p in RHO_P23H_PARAMETERS.values())


def test_h3_h4_adk_tools_provenance_and_nan_rejection(tmp_path):
    """H-3 & H-4: provenance_verify unpacks tuple properly and dataset_summary_statistics rejects NaN/Inf."""
    from virtual_lab.gateway.adk_tools import dataset_summary_statistics, provenance_verify

    res_nan = dataset_summary_statistics([1.0, float("nan"), 3.0])
    assert res_nan["status"] == "FAILED"

    db_path = str(tmp_path / "genesis.db")
    ledger = GenesisLedger(db_path)
    ledger.append("evt-1", Actor(type="SYSTEM", id="sys"), "INIT", {"ok": True})
    ledger.conn.close()

    ver = provenance_verify(db_path)
    assert ver["status"] == "COMPLETED"
    assert ver["verdict"] == "VERIFIED"
    assert ver["verified_event_count"] == 2


def test_h5_matter_units_offset_temperature_and_uncertainty():
    """H-5: Offset temperatures (degC) convert properly and uncertainties do not add 273.15 K."""
    from virtual_lab.matter.quantities import ScientificValue

    sv = ScientificValue(value=25.0, unit="degC", uncertainty=0.5)
    assert sv.canonical_value == pytest.approx(298.15)
    assert sv.canonical_uncertainty == pytest.approx(0.5)


def test_h6_jpeg_to_numpy_non_multiple_of_4_width():
    """H-6: jpeg_to_numpy handles image widths not divisible by 4 without row stride crash."""
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QColor, QImage
    from virtual_lab.instruments.analysis import jpeg_to_numpy

    img = QImage(641, 17, QImage.Format_RGB888)
    img.fill(QColor(120, 60, 200))
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "JPEG")
    jpeg_bytes = bytes(buf.data())

    arr = jpeg_to_numpy(jpeg_bytes)
    assert arr.shape == (17, 641, 3)


def test_h7_connection_failed_state_and_camera_frame_verification():
    """H-7: DeviceConnectionState returns ERROR when all channels are FAILED, and CameraFrameDecoder checks sha256/size."""
    from virtual_lab.instruments.connection import (
        ChannelConnectionState,
        DeviceConnectionState,
        InstrumentState,
        SensorChannelState,
    )
    from virtual_lab.instruments.transport.packet_parser import CameraFrameDecoder

    dev = DeviceConnectionState(
        device_id="DEV-ERR",
        sensors=ChannelConnectionState(
            channel_type="sensors",
            connection_id="C1",
            generation=1,
            socket=None,
            remote_address="127.0.0.1",
            connected_utc=0,
            state=SensorChannelState.FAILED,
        ),
    )
    assert dev.overall_state() == InstrumentState.ERROR

    decoder = CameraFrameDecoder()
    jpeg = b"\xff\xd8\xff\xd9"
    meta = {
        "message_type": "CAMERA_PREVIEW_FRAME",
        "schema_version": "1",
        "device_id": "DEV-1",
        "stream_id": "S-1",
        "camera_stream_key": {"camera_id": "0"},
        "frame_sequence": 1,
        "device_timestamp_ns": 100,
        "device_timebase": "MONOTONIC",
        "width": 10,
        "height": 10,
        "encoding": "JPEG",
        "orientation": 0,
        "lens_facing": "BACK",
        "focal_length_mm": 4.2,
        "representation": "ISP_PROCESSED",
        "payload_size_bytes": len(jpeg),
        "payload_sha256": "0" * 64,
    }
    meta_bytes = json.dumps(meta).encode("utf-8")
    raw = struct.pack(">I", len(meta_bytes)) + meta_bytes + jpeg
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        decoder.decode(raw)


def test_h8_observation_unit_scales_cover_temperature_and_voltage():
    """H-8: PhysicalDimension.TEMPERATURE, VOLTAGE, CURRENT, COUNT, and LIPOPHILICITY are registered in _UNIT_SCALES."""
    assert units_are_convertible("K", "°C", PhysicalDimension.TEMPERATURE) is True
    assert units_are_convertible("V", "mV", PhysicalDimension.VOLTAGE) is True
    assert units_are_convertible("A", "mA", PhysicalDimension.CURRENT) is True
    assert units_are_convertible("", "logP", PhysicalDimension.LIPOPHILICITY) is True
    assert units_are_convertible("", "count", PhysicalDimension.COUNT) is True


def test_h9_recasting_conflict_profile_includes_stale_voxels():
    """H-9: RecastingProfile.CONFLICT retains STALE voxels and records STALE resolution state in sidecar."""
    from virtual_lab.ai.memory.authoritative import AuthoritativeResolver
    from virtual_lab.ai.memory.models import AuthoritativeReference, EmbeddingMetadata, HyperVoxel
    from virtual_lab.ai.memory.recasting import RecastingEngine
    from virtual_lab.ai.memory.store import MemoryStore
    from virtual_lab.ai.memory.types import AuthoritativeResolutionState, MemoryClass
    from virtual_lab.ai.memory.views import BoundsSpec, LayoutSpec, RecastingProfile

    store = MemoryStore(":memory:")
    resolver = AuthoritativeResolver()
    emb = EmbeddingMetadata("M1", 2, "v1")
    ref = AuthoritativeReference("S", "T", "E1", entity_version="v1", content_hash="h1", experiment_id="EXP")
    store.upsert_voxel(HyperVoxel("V1", MemoryClass.SEMANTIC, ref, embedding=[1.0, 0.0], embedding_metadata=emb))
    # Register newer version in resolver so ref resolves to STALE
    resolver.register_mock_entity("S", "T", "E1", content_hash="h1", version="v2")
    assert resolver.resolve(ref) == AuthoritativeResolutionState.STALE

    engine = RecastingEngine(store, resolver)
    artifact, sidecar = engine.compile(
        query_vector=[1.0, 0.0],
        query_metadata=emb,
        query_text="conflict check",
        profile=RecastingProfile.CONFLICT,
        experiment_scope="EXP",
        bounds=BoundsSpec(10, 10, 2, 0.0),
        layout_spec=LayoutSpec("alg", "1", 42, "NONE"),
        activation_weight_set_id="w1",
    )
    assert len(sidecar.nodes) == 1
    assert sidecar.nodes[0].authoritative_resolution == "STALE"
    store.close()


def test_h10_streaming_envelope_parser_stops_at_closing_quote():
    """H-10: StreamingEnvelopeParser does not leak JSON syntax after the closing quote of 'text'."""
    from virtual_lab.ai.agent.streaming import StreamEventType, StreamingEnvelopeParser

    deltas = []
    parser = StreamingEnvelopeParser(lambda evt, data: deltas.append(data) if evt == StreamEventType.ANSWER_DELTA else None)
    for tok in ['{"type": "answer", ', '"text": "Hello ', 'world"', ', "extra": "ignored"}']:
        parser.feed(tok)
    assert "".join(deltas) == "Hello world"


def test_m2_prcc_handles_constant_parameter_column():
    """M-2: prcc returns finite 0.0 for zero-variance columns instead of NaN."""
    from virtual_lab.biological.analysis import prcc

    X = np.column_stack([np.ones(20), np.linspace(0, 1, 20)])
    y = 2.0 * X[:, 1]
    res = prcc(X, y)
    assert np.all(np.isfinite(res))
    assert res[0] == 0.0
    assert res[1] > 0.99


def test_m7_virtual_mass_spec_supports_sulfur_and_chlorine():
    """M-7: simulate_isotope_envelope supports S, P, F, Cl, Br in addition to C, H, N, O."""
    from virtual_lab.matter.virtual_mass_spec import simulate_isotope_envelope

    spec = simulate_isotope_envelope("C2H6OS")
    assert len(spec.peaks) >= 3
    assert spec.retained_probability == pytest.approx(1.0, abs=1e-4)
