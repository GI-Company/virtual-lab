"""Content-addressed results with a real ledger; created lazily when a run is saved."""
from pathlib import Path
import hashlib, json, os, uuid
from virtual_lab.core.ledger import GenesisLedger, Actor

class RunStore:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("VIRTUALLAB_DATA_DIR", Path.home()/"Library/Application Support/VirtualLab/cockpit"))

    def save(self, result):
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(result, sort_keys=True, separators=(",",":"), allow_nan=False).encode()
        digest = hashlib.sha256(payload).hexdigest()
        ledger = GenesisLedger(str(self.root/"ledger.db"))
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
        if not (self.root/"ledger.db").exists(): return []
        ledger = GenesisLedger(str(self.root/"ledger.db"))
        try:
            return [ledger._row_to_event(row).model_dump() for row in ledger.conn.execute("SELECT * FROM ledger_events ORDER BY sequence")]
        finally:
            ledger.conn.close()

    def load_all(self):
        runs=[]
        for event in self.events():
            if event["event_type"] not in ("SIMULATION_SAVED", "DESIGN_SAVED"): continue
            p=event["payload"]
            if p["file"] != p["sha256"]+".json" or len(p["sha256"]) != 64:
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
        ledger=GenesisLedger(str(self.root/"ledger.db"))
        try:
            target=self.root/(digest+".json")
            target.write_bytes(payload)
            ledger.append(str(uuid.uuid4()),Actor(type="USER",id="local-researcher"),"DESIGN_SAVED",
                          {"sha256":digest,"file":target.name})
            ledger.verify_chain()
        finally:ledger.conn.close()
        return str(target)
