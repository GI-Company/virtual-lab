import json
from pathlib import Path
import pytest
from virtual_lab.pilots.ms_workflow import import_centroid_csv, normalize_centroid_csv, verify_centroid_bundle
from virtual_lab.pilots.schemas import PilotError


def ingest(tmp_path):
    source = tmp_path / 'input.csv'
    source.write_bytes(b'mz,intensity\r\n101.00000000000000000001,2\r\n100,0\r\n101.00000000000000000001,2\r\n')
    return import_centroid_csv(source, tmp_path/'runs', sample_id='s', instrument_id='i', operator_id='o', approved_nonconfidential=True)


def test_exact_decimal_precision_and_duplicate_imports(tmp_path):
    first = ingest(tmp_path)
    second = ingest(tmp_path)
    a, b = (json.loads(p.read_bytes()) for p in (first, second))
    assert b['duplicate_of'] == [a['run_id']]
    assert b['mz_units'] is None and b['intensity_units'] is None
    assert a['source_sha256'] == b['source_sha256']
    normalized = (first.parent/'peaks.csv').read_bytes()
    assert normalized.count(b'101.00000000000000000001,2') == 2
    assert normalize_centroid_csv(normalized)[0] == normalized
    assert (first.parent/'source.csv').read_bytes() == (tmp_path/'input.csv').read_bytes()


@pytest.mark.parametrize('change', [
    {'epistemic_state':'MEASURED'}, {'approved_nonconfidential':1}, {'schema_version':2.0}, {'peak_count':True}, {'schema_version':True},
    {'sample_id':'../secret'}, {'acquired_at_utc':'2026-01-01'}, {'import_status':'failed'},
    {'source_sha256':'a'*64}, {'unexpected':'value'}, {'approved_nonconfidential':False},
])
def test_manifest_metadata_cannot_silently_change(tmp_path, change):
    path = ingest(tmp_path)
    data = json.loads(path.read_bytes())
    data.update(change)
    path.write_text(json.dumps(data))
    with pytest.raises(PilotError):
        verify_centroid_bundle(path)


def test_external_digest_detects_entire_valid_bundle_replacement(tmp_path):
    from hashlib import sha256
    first = ingest(tmp_path)
    anchor = sha256(first.read_bytes()).hexdigest()
    data = json.loads(first.read_bytes())
    data['sample_id'] = 'different-but-valid'
    first.write_text(json.dumps(data))
    assert verify_centroid_bundle(first)['verified']  # unsigned standalone contract
    with pytest.raises(PilotError, match='independently recorded'):
        verify_centroid_bundle(first, expected_manifest_sha256=anchor)


@pytest.mark.parametrize('payload', [b'mz,intensity\n1_000,2\n', b'mz,intensity\n1,2\n\n',
    b'mz,intensity\n"1,2\n', b'mz,intensity\n1e999999,2\n', b'mz,intensity\n1,=CMD()\n',
    b'mz,intensity\n1,\x00\n', b'mz,intensity\n1,NaN\n'])
def test_malicious_or_unsupported_numbers(payload):
    with pytest.raises(PilotError):
        normalize_centroid_csv(payload)


def test_symlink_source_parent_and_artifact_rejected(tmp_path):
    path = ingest(tmp_path)
    link = tmp_path/'linked'
    link.symlink_to(path.parent, target_is_directory=True)
    with pytest.raises(PilotError, match='Symbolic'):
        verify_centroid_bundle(link/'manifest.json')
    peak = path.parent/'peaks.csv'
    peak.unlink()
    peak.symlink_to(tmp_path/'input.csv')
    with pytest.raises(PilotError, match='Symbolic'):
        verify_centroid_bundle(path)


def test_bounds_and_failed_write_leave_no_complete_run(tmp_path, monkeypatch):
    from virtual_lab.pilots import ms_workflow as ms
    monkeypatch.setattr(ms, 'MAX_PEAKS', 1)
    with pytest.raises(PilotError) as exc:
        normalize_centroid_csv(b'mz,intensity\n1,2\n2,3\n')
    assert exc.value.code == 'ROW_LIMIT'
    monkeypatch.setattr(ms, 'MAX_PEAKS', 100000)
    source = tmp_path/'data.csv'
    source.write_text('mz,intensity\n1,2\n')
    monkeypatch.setattr(ms, 'write_private', lambda *args: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError):
        import_centroid_csv(source, tmp_path/'runs', sample_id='s', instrument_id='i', operator_id='o', approved_nonconfidential=True)
    assert not list((tmp_path/'runs').iterdir())


def test_duplicate_json_key_and_large_manifest_rejected(tmp_path):
    path = ingest(tmp_path)
    path.write_bytes(path.read_bytes().replace(b'"schema_version": 2', b'"schema_version": 2, "schema_version": 2'))
    with pytest.raises(PilotError):
        verify_centroid_bundle(path)
    path.write_bytes(b' '*65537)
    with pytest.raises(PilotError) as exc:
        verify_centroid_bundle(path)
    assert exc.value.code == 'SIZE_LIMIT'


def test_normalization_handles_bounded_extreme_precision():
    raw = ('mz,intensity\n1.' + '1'*97 + 'e-100,0\n').encode()
    normalized, count = normalize_centroid_csv(raw)
    assert count == 1 and normalize_centroid_csv(normalized)[0] == normalized


def test_source_changed_after_preview_rejected(tmp_path):
    source = tmp_path/'input.csv'
    source.write_text('mz,intensity\n100,2\n')
    with pytest.raises(PilotError, match='preview'):
        import_centroid_csv(source, tmp_path/'runs', sample_id='s', instrument_id='i', operator_id='o',
            approved_nonconfidential=True, expected_source_sha256='0'*64)
    assert not (tmp_path/'runs').exists()


def test_oversized_file_and_nonregular_file_rejected(tmp_path):
    import os
    from virtual_lab.pilots.schemas import MAX_SOURCE_BYTES
    from virtual_lab.pilots.storage import read_bounded
    source = tmp_path/'oversized.csv'
    with source.open('wb') as stream:
        stream.truncate(MAX_SOURCE_BYTES + 1)
    with pytest.raises(PilotError) as exc:
        read_bounded(source, MAX_SOURCE_BYTES)
    assert exc.value.code == 'SIZE_LIMIT'
    if hasattr(os, 'mkfifo'):
        fifo = tmp_path/'pipe.csv'
        os.mkfifo(fifo)
        with pytest.raises(PilotError) as exc:
            read_bounded(fifo, MAX_SOURCE_BYTES)
        assert exc.value.code == 'UNSAFE_PATH'
