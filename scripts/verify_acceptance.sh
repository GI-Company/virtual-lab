#!/usr/bin/env bash
set -e

export PYTHONPATH=.

echo "=== Creating genesis.db ==="
rm -f genesis.db
mkdir -p poc_bundle
rm -f poc_bundle/genesis.db
.venv/bin/python -c '
from virtual_lab.core.ledger import GenesisLedger, Actor
l = GenesisLedger("poc_bundle/genesis.db")
a = Actor(type="TEST", id="sys")
l.append("evt1", a, "TEST", {"foo": "bar"})
'
echo "dummy artifact" > poc_bundle/dummy.txt

echo "=== Building pristine.vlab ==="
.venv/bin/python scripts/build_vlab_bundle.py poc_bundle pristine.vlab > /dev/null

echo "=== Verifying pristine.vlab ==="
.venv/bin/python virtual_lab/cli/verify.py pristine.vlab

echo "=== Building missing_artifact.vlab ==="
.venv/bin/python scripts/build_vlab_bundle.py poc_bundle missing_artifact.vlab > /dev/null
zip -d missing_artifact.vlab "manifest.json" > /dev/null || true

echo "=== Verifying missing_artifact.vlab ==="
if .venv/bin/python virtual_lab/cli/verify.py missing_artifact.vlab; then
  echo "FAIL: missing_artifact.vlab verification succeeded unexpectedly."
  exit 1
else
  echo "PASS: missing_artifact.vlab verification failed as expected."
fi

echo "=== Building artifact_byte_changed.vlab ==="
cp pristine.vlab artifact_byte_changed.vlab
mkdir -p tmp_abc
cd tmp_abc
unzip -q -o ../artifact_byte_changed.vlab
echo "tampered" >> genesis.db
zip -q -r ../artifact_byte_changed.vlab .
cd ..
rm -rf tmp_abc

echo "=== Verifying artifact_byte_changed.vlab ==="
if .venv/bin/python virtual_lab/cli/verify.py artifact_byte_changed.vlab; then
  echo "FAIL: artifact_byte_changed.vlab verification succeeded unexpectedly."
  exit 1
else
  echo "PASS: artifact_byte_changed.vlab verification failed as expected."
fi

echo "=== Building genesis_event_changed.vlab ==="
cp pristine.vlab genesis_event_changed.vlab
mkdir -p tmp_gec
cd tmp_gec
unzip -q -o ../genesis_event_changed.vlab
sqlite3 genesis.db "DROP TRIGGER prevent_ledger_update; UPDATE ledger_events SET payload_json='{\"foo\": \"tampered\"}' WHERE event_id='evt1';"
zip -q -r ../genesis_event_changed.vlab .
cd ..
rm -rf tmp_gec

echo "=== Verifying genesis_event_changed.vlab ==="
if .venv/bin/python virtual_lab/cli/verify.py genesis_event_changed.vlab; then
  echo "FAIL: genesis_event_changed.vlab verification succeeded unexpectedly."
  exit 1
else
  echo "PASS: genesis_event_changed.vlab verification failed as expected."
fi

echo "ALL TESTS PASSED."
