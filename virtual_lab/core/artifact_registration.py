import os
import base64
import hashlib
from datetime import datetime, timezone
import logging
from typing import Optional

from virtual_lab.core.ledger import GenesisLedger, ChainIntegrityError
from virtual_lab.instruments.transport.protocol_v1 import ArtifactRegister, LedgerRegistered, LedgerRejected

logger = logging.getLogger(__name__)

class ArtifactRegistrationService:
    def __init__(self, ledger: GenesisLedger):
        self.ledger = ledger
        self.artifacts_dir = os.path.abspath(os.path.join(os.getcwd(), ".virtuallab", "artifacts"))
        os.makedirs(self.artifacts_dir, exist_ok=True)

    def _create_rejection(self, request: ArtifactRegister, reason: str, error_message: str, claimed_sha: Optional[str] = None) -> str:
        return LedgerRejected(
            device_id=request.device_id,
            measurement_id=request.measurement_id,
            artifact_id=request.artifact_id,
            correlation_id=request.correlation_id,
            claimed_artifact_sha256=claimed_sha,
            reason=reason,
            error_message=error_message
        ).model_dump_json()

    def handle_registration(self, request: ArtifactRegister, connection_device_id: str) -> str:
        """
        Handles an ARTIFACT_REGISTER request. Returns a JSON string of LedgerRegistered or LedgerRejected.
        """
        # 1. Enforce Control Socket Identity
        if request.device_id != connection_device_id:
            return self._create_rejection(request, "IDENTITY_CONFLICT", f"Device ID {request.device_id} does not match socket identity {connection_device_id}")

        try:
            # 2. Strict Base64 Decoding
            payload_bytes = base64.b64decode(request.payload_base64, validate=True)
        except Exception as e:
            return self._create_rejection(request, "INVALID_PAYLOAD_ENCODING", "Malformed Base64 payload encoding.")

        # 3. Payload size check
        if len(payload_bytes) != request.size_bytes:
            return self._create_rejection(request, "SIZE_MISMATCH", f"Decoded size {len(payload_bytes)} does not match claimed {request.size_bytes}")

        # 4. Hash verification
        actual_sha256 = hashlib.sha256(payload_bytes).hexdigest()
        if actual_sha256 != request.edge_sha256:
            return self._create_rejection(request, "DIGEST_CONFLICT", f"Payload hash {actual_sha256} does not match edge hash {request.edge_sha256}", claimed_sha=request.edge_sha256)

        # 5. Idempotency Check
        target_file = os.path.join(self.artifacts_dir, f"{request.artifact_id}.json")
        existing_event = self.ledger.find_artifact_registration(request.artifact_id)
        
        if existing_event:
            existing_payload = existing_event.payload
            
            if existing_payload.get("device_id") != request.device_id:
                return self._create_rejection(request, "IDENTITY_CONFLICT", f"Artifact {request.artifact_id} is already registered to a different device.", claimed_sha=actual_sha256)

            if existing_payload.get("measurement_id") != request.measurement_id:
                return self._create_rejection(request, "IDENTITY_CONFLICT", f"Artifact {request.artifact_id} is already registered to a different measurement.", claimed_sha=actual_sha256)
                
            if existing_payload.get("artifact_sha256") != actual_sha256:
                return self._create_rejection(request, "DIGEST_CONFLICT", "Artifact digest conflict with existing registration.", claimed_sha=actual_sha256)
                
            if not os.path.exists(target_file):
                return self._create_rejection(request, "ARTIFACT_MISSING", "Ledger event exists but artifact file is missing.", claimed_sha=actual_sha256)
                
            with open(target_file, "rb") as f:
                disk_bytes = f.read()
            if hashlib.sha256(disk_bytes).hexdigest() != actual_sha256:
                return self._create_rejection(request, "ARTIFACT_INTEGRITY_FAILURE", "Ledger event exists but artifact file hash mismatch.", claimed_sha=actual_sha256)

            # Identical request: Replay original acknowledgement
            ack = LedgerRegistered(
                device_id=request.device_id,
                measurement_id=request.measurement_id,
                artifact_id=request.artifact_id,
                correlation_id=request.correlation_id,
                artifact_sha256=actual_sha256,
                vlab_artifact_ref=existing_payload.get("vlab_artifact_ref", ""),
                ledger_event_id=existing_event.event_id,
                ledger_event_hash=existing_event.event_hash,
                registered_at_utc=existing_payload.get("registered_at_utc", "")
            )
            return ack.model_dump_json()

        # 6. Immutable Artifact Finalization
        if os.path.exists(target_file):
            with open(target_file, "rb") as f:
                disk_bytes = f.read()
            if hashlib.sha256(disk_bytes).hexdigest() == actual_sha256:
                # Orphan file matches exactly. Skip writing.
                pass
            else:
                return self._create_rejection(request, "IMMUTABLE_ARTIFACT_CONFLICT", "Target artifact file already exists with different contents.", claimed_sha=actual_sha256)
        else:
            temp_file = os.path.join(self.artifacts_dir, f"{request.artifact_id}.tmp")
            try:
                with open(temp_file, "wb") as f:
                    f.write(payload_bytes)
                    f.flush()
                    os.fsync(f.fileno())
                # Race safe atomic finalization via exclusive create
                fd = os.open(target_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "wb") as final_f:
                    final_f.write(payload_bytes)
                    final_f.flush()
                    os.fsync(final_f.fileno())
                os.remove(temp_file)
            except FileExistsError:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                # Another process won the race
                with open(target_file, "rb") as f:
                    disk_bytes = f.read()
                if hashlib.sha256(disk_bytes).hexdigest() != actual_sha256:
                    return self._create_rejection(request, "IMMUTABLE_ARTIFACT_CONFLICT", "Target artifact file was concurrently written with different contents.", claimed_sha=actual_sha256)
            except Exception as e:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                return self._create_rejection(request, "STORAGE_FAILURE", f"Failed to persist artifact: {str(e)}", claimed_sha=actual_sha256)

        # Read back and verify once more
        with open(target_file, "rb") as f:
            final_bytes = f.read()
        if hashlib.sha256(final_bytes).hexdigest() != actual_sha256:
            os.remove(target_file)
            return self._create_rejection(request, "STORAGE_INTEGRITY_FAILURE", "Post-persistence validation failed", claimed_sha=actual_sha256)

        vlab_ref = f"vlab://artifacts/{request.artifact_id}.json"
        registered_at = datetime.now(timezone.utc).isoformat()

        # 7. GenesisLedger append
        event_payload = {
            "artifact_id": request.artifact_id,
            "measurement_id": request.measurement_id,
            "correlation_id": request.correlation_id,
            "device_id": request.device_id,
            "artifact_sha256": actual_sha256,
            "vlab_artifact_ref": vlab_ref,
            "registered_at_utc": registered_at
        }
        
        try:
            event_hash = self.ledger.append_artifact_registration(event_payload)
            evt = self.ledger.find_artifact_registration(request.artifact_id)
            if not evt:
                raise Exception("Ledger append succeeded but could not read back")
            event_id = evt.event_id
        except ChainIntegrityError as e:
            return self._create_rejection(request, "LEDGER_INTEGRITY_FAILURE", str(e), claimed_sha=actual_sha256)

        ack = LedgerRegistered(
            device_id=request.device_id,
            measurement_id=request.measurement_id,
            artifact_id=request.artifact_id,
            correlation_id=request.correlation_id,
            artifact_sha256=actual_sha256,
            vlab_artifact_ref=vlab_ref,
            ledger_event_id=event_id,
            ledger_event_hash=event_hash,
            registered_at_utc=registered_at
        )
        return ack.model_dump_json()
