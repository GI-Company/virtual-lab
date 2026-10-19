"""Build and verify isolated signed-bundle acceptance fixtures."""

import argparse
from pathlib import Path
import sqlite3
import tempfile
import zipfile

from scripts.build_vlab_bundle import build_vlab_bundle
from virtual_lab.core.ledger import Actor, GenesisLedger
from virtual_lab.core.provenance_export import explain_provenance


def create_acceptance_bundles(output_dir):
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary)
        ledger = GenesisLedger(str(source / "genesis.db"))
        try:
            ledger.append("acceptance-event", Actor(type="TEST", id="acceptance"), "TEST", {"foo": "bar"})
        finally:
            ledger.conn.close()
        (source / "dummy.txt").write_text("dummy artifact\n")
        pristine = root / "pristine.vlab"
        build_vlab_bundle(str(source), str(pristine))
        for name in ("missing_artifact", "artifact_byte_changed"):
            with zipfile.ZipFile(pristine) as original, zipfile.ZipFile(root / f"{name}.vlab", "w") as changed:
                for entry in original.infolist():
                    if entry.filename == "dummy.txt" and name == "missing_artifact":
                        continue
                    data = original.read(entry.filename)
                    if entry.filename == "dummy.txt":
                        data += b"tampered\n"
                    changed.writestr(entry, data)
        # Re-sign the manifest so this case exercises ledger verification,
        # independently of ZIP artifact-hash validation.
        with sqlite3.connect(source / "genesis.db") as database:
            database.execute("DROP TRIGGER prevent_ledger_update")
            database.execute("UPDATE ledger_events SET payload_json = ? WHERE event_id = ?",
                             ('{"foo":"tampered"}', "acceptance-event"))
        build_vlab_bundle(str(source), str(root / "genesis_event_changed.vlab"))
    return {name: root / f"{name}.vlab" for name in
            ("pristine", "missing_artifact", "artifact_byte_changed", "genesis_event_changed")}


def verify_acceptance(output_dir):
    bundles = create_acceptance_bundles(output_dir)
    for name, bundle in bundles.items():
        report = explain_provenance(str(bundle))
        valid = "Genesis hash chain: VERIFIED" in report and "Error:" not in report and "[WARNING]" not in report
        if valid != (name == "pristine"):
            raise RuntimeError(f"Unexpected verification result for {name}:\n{report}")
        print(f"PASS: {name} {'verified' if valid else 'rejected'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Keep generated fixtures in this directory")
    args = parser.parse_args()
    if args.output_dir is not None:
        verify_acceptance(args.output_dir)
    else:
        with tempfile.TemporaryDirectory() as temporary:
            verify_acceptance(temporary)


if __name__ == "__main__":
    main()
