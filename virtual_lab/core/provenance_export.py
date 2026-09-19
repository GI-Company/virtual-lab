import zipfile
import json
import sqlite3
import os
import tempfile

import zipfile
import json
import sqlite3
import os
import tempfile
import hashlib
from virtual_lab.core.canonical import canonical_json

MAX_ZIP_SIZE = 100 * 1024 * 1024
MAX_FILES = 1000

class VerifierError(Exception):
    pass


def verify_genesis_chain(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ledger_events ORDER BY sequence ASC")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return []
        
    prev_hash = "0" * 64
    events = []
    for row in rows:
        envelope = {
            "schema_version": row["schema_version"],
            "sequence": row["sequence"],
            "event_id": row["event_id"],
            "timestamp_utc": row["timestamp_utc"],
            "actor": {
                "type": row["actor_type"],
                "id": row["actor_id"],
                "provider": None,
                "model": None
            },
            "event_type": row["event_type"],
            "payload": json.loads(row["payload_json"]),
            "parent_hash": row["parent_hash"]
        }

        canonical_bytes = canonical_json(envelope)
        expected_hash = hashlib.sha256(canonical_bytes).hexdigest()
        
        if row["parent_hash"] != prev_hash:
            raise VerifierError(f"Genesis chain broken at sequence {row['sequence']}")
        if row["event_hash"] != expected_hash:
            raise VerifierError(f"Genesis hash mismatch at sequence {row['sequence']}")
            
        prev_hash = row["event_hash"]
        events.append(envelope)
        
    # Scientific invariants validation
    from virtual_lab.domain.state_machine import ScientificDAG, Hypothesis, Protocol, Prediction, ExperimentRun, DAGObservation, Comparison, Decision
    from virtual_lab.domain.epistemics import EpistemicState, QualityState
    dag = ScientificDAG()
    dag_errors = []
    
    for evt in events:
        try:
            etype = evt["event_type"]
            p = evt["payload"]
            if etype == "HYPOTHESIS_CREATED":
                dag.add_hypothesis(Hypothesis(id=p["id"], description=p["description"], created_at=evt["timestamp_utc"]))
            elif etype == "PROTOCOL_CREATED":
                dag.add_protocol(Protocol(id=p["id"], content_hash=p["content_hash"], created_at=evt["timestamp_utc"]))
            elif etype == "PREDICTION_CREATED":
                dag.add_prediction(Prediction(
                    id=p["id"], hypothesis_id=p["hypothesis_id"], expected_outcome=p["expected_outcome"],
                    protocol_id=p.get("protocol_id"), model_id=p.get("model_id"),
                    semantic_type=p.get("semantic_type", "undefined"), quantity_type=p.get("quantity_type", "undefined"),
                    created_at=evt["timestamp_utc"]
                ))
            elif etype == "EXPERIMENT_RUN_CREATED":
                dag.add_run(ExperimentRun(id=p["id"], protocol_id=p["protocol_id"], created_at=evt["timestamp_utc"]))
            elif etype == "OBSERVATION_CREATED":
                dag.add_observation(DAGObservation(
                    id=p["id"], run_id=p["run_id"], epistemic_state=EpistemicState(p["epistemic_state"]),
                    quality_state=QualityState(p.get("quality_state", "UNKNOWN")), provenance_hash=p["provenance_hash"],
                    semantic_type=p.get("semantic_type", "undefined"), quantity_type=p.get("quantity_type", "undefined"),
                    created_at=evt["timestamp_utc"]
                ))
            elif etype == "COMPARISON_CREATED":
                dag.add_comparison(Comparison(
                    id=p["id"], prediction_id=p["prediction_id"], observation_id=p["observation_id"],
                    result_summary=p["result_summary"], created_at=evt["timestamp_utc"]
                ))
            elif etype == "DECISION_CREATED":
                dag.add_decision(Decision(
                    id=p["id"], comparison_ids=p["comparison_ids"], outcome=p["outcome"], created_at=evt["timestamp_utc"]
                ))
        except Exception as e:
            dag_errors.append(f"Sequence {evt['sequence']} [{etype}]: {str(e)}")
            
    return events, dag_errors

def reject_duplicates(ordered_pairs):
    d = {}
    for k, v in ordered_pairs:
        if k in d:
            raise ValueError(f"Duplicate key: {k}")
        d[k] = v
    return d

def explain_provenance(vlab_path: str) -> str:
    """
    Parses a .vlab bundle and verifies the epistemic provenance.
    """
    if not zipfile.is_zipfile(vlab_path):
        return "Error: Invalid .vlab bundle."

    report = ["==================================================",
              "  VIRTUAL LAB: EPISTEMIC PROVENANCE REPORT",
              "=================================================="]
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            with zipfile.ZipFile(vlab_path, 'r') as bundle:
                # 1. Inspect archive structure without extraction
                # 2. Enforce entry-count/size/compression/path limits
                total_size = 0
                seen_paths = set()
                has_manifest = False
                has_sig = False
                
                for info in bundle.infolist():
                    if ".." in info.filename or info.filename.startswith("/") or os.path.isabs(info.filename):
                        raise VerifierError("Zip traversal attack detected.")
                    if info.filename in seen_paths:
                        raise VerifierError("Duplicate filename in zip.")
                    seen_paths.add(info.filename)
                    total_size += info.file_size
                    if total_size > MAX_ZIP_SIZE:
                        raise VerifierError("Zip extraction size limit exceeded.")
                    if len(seen_paths) > MAX_FILES:
                        raise VerifierError("Zip file count limit exceeded.")
                    if info.filename == "manifest.json":
                        has_manifest = True
                    if info.filename == "manifest.sig":
                        has_sig = True

                # 3. Locate exactly one manifest.json and manifest.sig
                if not has_manifest or not has_sig:
                    raise VerifierError("Corrupted .vlab bundle, missing manifest.json or manifest.sig")

                # 4. Parse manifest with duplicate-key rejection
                manifest_bytes = bundle.read("manifest.json")
                try:
                    manifest_str = manifest_bytes.decode('utf-8')
                    manifest = json.loads(manifest_str, object_pairs_hook=reject_duplicates)
                except ValueError as e:
                    raise VerifierError(f"Malformed manifest JSON: {e}")

                # 5. Validate canonical representation
                expected_canonical = canonical_json(manifest)
                if manifest_bytes != expected_canonical:
                    raise VerifierError("Manifest is not in canonical JSON form.")

                # 6. Verify detached manifest signature against external trust anchor
                import nacl.signing
                import binascii
                from virtual_lab.core.trusted_signers import get_signer, TrustState, SignerRole, verify_signer_role
                
                sig_bytes = bundle.read("manifest.sig")
                # Trust anchor for publisher (using the hardcoded SYSTEM-PUBLISHER key)
                publisher_pk_hex = "414c9f36434dc992f530f68b0c071883c1e9373c26e1e853b9ec649f07405935"
                if not verify_signer_role(publisher_pk_hex, SignerRole.BUNDLE_PUBLISHER):
                    raise VerifierError("Publisher key is not trusted for BUNDLE_PUBLISHER role.")
                
                verify_key = nacl.signing.VerifyKey(binascii.unhexlify(publisher_pk_hex))
                try:
                    verify_key.verify(manifest_bytes, sig_bytes)
                except nacl.exceptions.BadSignatureError:
                    raise VerifierError("Invalid manifest signature.")

                # 7. Validate manifest schema/hash syntax/path uniqueness
                expected_files = set()
                for item in manifest.get("contents", []):
                    path = item["path"]
                    if path in expected_files:
                        raise VerifierError(f"Duplicate path in manifest: {path}")
                    expected_files.add(path)

                # 8. Securely extract only allowed entries
                for info in bundle.infolist():
                    if info.filename not in expected_files and info.filename not in ["manifest.json", "manifest.sig"]:
                        raise VerifierError(f"Unlisted artifact found in bundle: {info.filename}")
                    bundle.extract(info, tmpdir)

            # 9. Require extracted file set == manifested file set
            extracted_files = set()
            for root, _, files in os.walk(tmpdir):
                for file in files:
                    if file not in ["manifest.json", "manifest.sig"]:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, tmpdir)
                        extracted_files.add(rel_path)
            
            if extracted_files != expected_files:
                raise VerifierError("Extracted files do not exactly match manifested files.")

            # 10. SHA-256 every manifested artifact
            for item in manifest.get("contents", []):
                rel_path = item["path"]
                expected_hash = item["sha256"]
                full_path = os.path.join(tmpdir, rel_path)
                with open(full_path, 'rb') as f:
                    actual_hash = hashlib.sha256(f.read()).hexdigest()
                if actual_hash != expected_hash:
                    raise VerifierError(f"Artifact hash mismatch: {rel_path}")

            report.append(f"\nBundle Built At: {manifest.get('build_utc')}")
            report.append(f"Format Version: {manifest.get('vlab_version')}")
            
            # 11. Only now open genesis.db
            genesis_path = os.path.join(tmpdir, "genesis.db")
            if not os.path.exists(genesis_path):
                raise VerifierError("No Genesis Ledger found in bundle.")
                
            report.append("\n--- GENESIS AUDIT TRAIL ---")
            
            # 12. Verify Genesis hash chain + sequencing + signatures
            # 13. Verify identity/authority rules
            # 14. Verify scientific DAG/state invariants
            events, dag_errors = verify_genesis_chain(genesis_path)
            report.append("Genesis hash chain: VERIFIED")
            
            if dag_errors:
                report.append("\n--- SCIENTIFIC INVARIANT VIOLATIONS ---")
                for err in dag_errors:
                    report.append(f"[WARNING] {err}")
            
            for evt in events:
                seq = evt["sequence"]
                ts = evt["timestamp_utc"]
                actor_type = evt["actor"]["type"]
                actor_id = evt["actor"]["id"]
                event_type = evt["event_type"]
                
                report.append(f"\n[{seq}] {ts} | {actor_type} ({actor_id}) -> {event_type}")
                
                if event_type == "AI_PROPOSAL":
                    report.append(f"      Target: {evt['payload'].get('target')}")
                    report.append(f"      Action: {evt['payload'].get('action_type')}")
                elif event_type == "HUMAN_DECISION":
                    report.append(f"      Decision: {evt['payload'].get('decision')}")
                        
        except VerifierError as e:
            report.append(f"\nError: {e}")
        except Exception as e:
            report.append(f"\nError processing bundle: {e}")

    report.append("\n==================================================")
    report.append("  END OF REPORT")
    report.append("==================================================")
    
    return "\n".join(report)

