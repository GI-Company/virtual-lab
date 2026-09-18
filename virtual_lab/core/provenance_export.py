import zipfile
import json
import sqlite3
import os
import tempfile

def explain_provenance(vlab_path: str) -> str:
    """
    Parses a .vlab bundle and generates a human-readable text report of the 
    epistemic provenance of the results contained within.
    """
    if not zipfile.is_zipfile(vlab_path):
        return "Error: Invalid .vlab bundle."

    report = []
    report.append("==================================================")
    report.append("  VIRTUAL LAB: EPISTEMIC PROVENANCE REPORT")
    report.append("==================================================")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(vlab_path, 'r') as bundle:
            bundle.extractall(tmpdir)
            
            manifest_path = os.path.join(tmpdir, "manifest.json")
            if not os.path.exists(manifest_path):
                return "Error: Corrupted .vlab bundle, missing manifest.json"
                
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
                
            report.append(f"\nBundle Built At: {manifest.get('build_utc')}")
            report.append(f"Format Version: {manifest.get('vlab_version')}")
            
            genesis_path = os.path.join(tmpdir, "genesis.db")
            if not os.path.exists(genesis_path):
                report.append("\n[WARNING] No Genesis Ledger found in bundle.")
                return "\n".join(report)
                
            report.append("\n--- GENESIS AUDIT TRAIL ---")
            conn = sqlite3.connect(genesis_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            try:
                cursor.execute("SELECT * FROM ledger_events ORDER BY sequence ASC")
                events = cursor.fetchall()
                
                for event in events:
                    seq = event["sequence"]
                    ts = event["timestamp_utc"]
                    actor_type = event["actor_type"]
                    actor_id = event["actor_id"]
                    event_type = event["event_type"]
                    
                    report.append(f"\n[{seq}] {ts} | {actor_type} ({actor_id}) -> {event_type}")
                    
                    if event_type == "AI_PROPOSAL":
                        payload = json.loads(event["payload_json"])
                        report.append(f"      Target: {payload.get('target')}")
                        report.append(f"      Action: {payload.get('action_type')}")
                        report.append(f"      Epistemic State: {payload.get('epistemic_state')} (Authoritative: {payload.get('authoritative')})")
                    
                    elif event_type == "HUMAN_DECISION":
                        payload = json.loads(event["payload_json"])
                        report.append(f"      Decision: {payload.get('decision')}")
                        
            except sqlite3.Error as e:
                report.append(f"Error reading genesis ledger: {e}")
            finally:
                conn.close()

    report.append("\n==================================================")
    report.append("  END OF REPORT")
    report.append("==================================================")
    
    return "\n".join(report)
