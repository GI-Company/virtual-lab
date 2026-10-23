"""Content-addressed results with a real ledger; created lazily when a run is saved."""
from pathlib import Path
import hashlib, json, os, uuid
from virtual_lab.core.ledger import GenesisLedger, Actor

class RunStore:
    def __init__(self, root=None):
        from virtual_lab.core.paths import app_data_dir
        self.root = Path(root) if root is not None else app_data_dir()

    def _ledger_path(self) -> Path:
        return self.root / "genesis.db"

    def save(self, result):
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(result, sort_keys=True, separators=(",",":"), allow_nan=False).encode()
        digest = hashlib.sha256(payload).hexdigest()
        ledger = GenesisLedger(str(self._ledger_path()))
        try:
            target = self.root/(digest+".json")
            temp = self.root/("."+str(uuid.uuid4())+".tmp")
            try:
                temp.write_bytes(payload)
                temp.replace(target)
            finally:
                temp.unlink(missing_ok=True)
            ledger.append(str(uuid.uuid4()), Actor(type="USER",id="local-researcher"), "SIMULATION_SAVED",
                          {"run_id":result["id"],"sha256":digest,"file":target.name})
            ledger.verify_chain()
        finally:
            ledger.conn.close()
        return str(target)

    def events(self):
        from virtual_lab.core.ledger import read_ledger_events
        events = []
        for name in ('ledger.db', 'genesis.db'):
            path = self.root / name
            if not path.exists():
                continue
            history = read_ledger_events(path)
            ledger_id = history[0].event_hash if history else name
            for event in history:
                value = event.model_dump()
                value.update(source_ledger=name, ledger_id=ledger_id,
                             event_key=name + ':' + ledger_id + ':' + event.event_id)
                events.append(value)
        return events

    def load_all(self):
        runs=[]
        for event in self.events():
            if event["event_type"] not in ("SIMULATION_SAVED", "DESIGN_SAVED"): continue
            p=event["payload"]
            if p["file"] != p["sha256"]+".json" or len(p["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in p["sha256"]):
                raise ValueError("Invalid artifact reference")
            data=(self.root/p["file"]).read_bytes()
            if hashlib.sha256(data).hexdigest() != p["sha256"]:
                raise ValueError("Saved result hash mismatch")
            result=json.loads(data)
            if event["event_type"] == "DESIGN_SAVED": continue
            if result["id"] != p["run_id"]: raise ValueError("Run identity mismatch")
            runs.append(result)
        return runs

    def save_design(self, design):
        self.root.mkdir(parents=True,exist_ok=True)
        payload=json.dumps(design,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
        digest=hashlib.sha256(payload).hexdigest()
        ledger=GenesisLedger(str(self._ledger_path()))
        try:
            target=self.root/(digest+".json")
            target.write_bytes(payload)
            ledger.append(str(uuid.uuid4()),Actor(type="USER",id="local-researcher"),"DESIGN_SAVED",
                          {"sha256":digest,"file":target.name})
            ledger.verify_chain()
        finally:ledger.conn.close()
        return str(target)
