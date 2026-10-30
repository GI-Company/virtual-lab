"""Opt-in workflow tests against user-supplied public CSVs; no spectra are committed."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import zipfile
from decimal import Decimal
import pytest
from virtual_lab.pilots.ms_workflow import import_centroid_csv, normalize_centroid_csv, verify_centroid_bundle, load_manifest
from virtual_lab.pilots.schemas import PilotError

ZIP_PATH=os.environ.get('VIRTUALLAB_PUBLIC_MS_ZIP')
if not ZIP_PATH:
    pytest.skip('Set VIRTUALLAB_PUBLIC_MS_ZIP to run supplied public-spectrum tests',allow_module_level=True)
with zipfile.ZipFile(ZIP_PATH) as archive:
    entries=archive.infolist()
    if len(entries)>100 or sum(e.file_size for e in entries)>32*1024*1024 or len({e.filename for e in entries})!=len(entries):
        raise ValueError('Public sample archive exceeds limits or has duplicates')
    for entry in entries:
        name=PurePosixPath(entry.filename)
        if len(name.parts)!=1 or str(name)!=entry.filename or '\\' in entry.filename or entry.file_size>16*1024*1024:
            raise ValueError('Unexpected public sample archive entry')
    with archive.open('source_manifest.json') as stream: manifest_raw=stream.read(65537)
    if len(manifest_raw)>65536: raise ValueError('Source manifest exceeds limits')
    RECORDS=json.loads(manifest_raw)
    if not isinstance(RECORDS,list) or not 1<=len(RECORDS)<=3: raise ValueError('Expected up to three sample records')
    SAMPLES=[]
    for record in RECORDS:
        name=record['filename']
        if PurePosixPath(name).name!=name or not name.endswith('.csv'): raise ValueError('Invalid source manifest filename')
        with archive.open(name) as stream: raw=stream.read(16*1024*1024+1)
        if hashlib.sha256(raw).hexdigest()!=record['sha256']: raise ValueError('Supplied source checksum mismatch')
        SAMPLES.append((record,raw))


def metadata(record):
    return dict(dataset_id=record['massbank_accession'],sample_id='reference-'+record['massbank_accession'],
        instrument_id='public-record-instrument',operator_id='local-test-runner',data_origin='public_reference',approved_nonconfidential=True)


def parse(raw):
    return [tuple(Decimal(v) for v in row) for row in list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))[1:]]


@pytest.mark.parametrize('record,raw',SAMPLES,ids=[r['massbank_accession'] for r,_ in SAMPLES])
def test_full_public_dataset_workflow(service,tmp_path,record,raw):
    from virtual_lab.pilots.reporting import verify_report_files
    source=tmp_path/record['filename'];source.write_bytes(raw)
    obs=service.import_csv(source,experiment_id='exp',**metadata(record))
    path=Path(obs.artifact_path)
    assert (path.parent/'source.csv').read_bytes()==raw
    manifest=load_manifest(path)
    assert manifest['peak_count']==record['peak_count'] and manifest['source_sha256']==record['sha256']
    assert manifest['acquired_at_utc'] is None and manifest['intensity_units'] is None
    assert manifest['data_origin']=='public_reference' and manifest['epistemic_state']=='UNKNOWN'
    assert service.reprocess(obs.session_id)['identical']
    assert service.test_alteration(obs.session_id)['detected']
    service.review(obs.session_id,reviewer='test-reviewer',approved=True,note='Public reference workflow checks only')
    report=service.export_report(obs.session_id,tmp_path/'report.pdf')
    result=json.loads(report.with_suffix('.json').read_bytes())
    assert result['workflow_check_status']=='PASS' and result['summary']['peak_count']==record['peak_count']
    assert result['manifest']['epistemic_state']=='UNKNOWN'
    assert verify_report_files(report.with_suffix('.sha256'))['verified']
    again=service.import_csv(source,experiment_id='exp',**metadata(record))
    assert obs.session_id in load_manifest(again.artifact_path)['duplicate_of']


@pytest.mark.parametrize('variant',['bom','crlf','reversed','quoted','exponents'])
@pytest.mark.parametrize('record,raw',SAMPLES,ids=[r['massbank_accession'] for r,_ in SAMPLES])
def test_equivalent_representations_normalize_identically(record,raw,variant):
    rows=list(csv.reader(io.StringIO(raw.decode())))
    if variant=='bom': changed=b'\xef\xbb\xbf'+raw
    elif variant=='crlf': changed=raw.replace(b'\n',b'\r\n')
    else:
        output=io.StringIO(newline='')
        writer=csv.writer(output,lineterminator='\n',quoting=csv.QUOTE_ALL if variant=='quoted' else csv.QUOTE_MINIMAL)
        writer.writerow(rows[0])
        values=rows[1:][::-1] if variant=='reversed' else rows[1:]
        for row in values: writer.writerow([format(Decimal(v),'e') for v in row] if variant=='exponents' else row)
        changed=output.getvalue().encode()
    assert normalize_centroid_csv(changed)[0]==normalize_centroid_csv(raw)[0]


@pytest.mark.parametrize('extra',['duplicate','zero_intensity'])
@pytest.mark.parametrize('record,raw',SAMPLES,ids=[r['massbank_accession'] for r,_ in SAMPLES])
def test_duplicate_centroids_and_zero_intensity_remain(record,raw,extra):
    rows=list(csv.reader(io.StringIO(raw.decode())))
    added=rows[1] if extra=='duplicate' else [rows[1][0],'0']
    output=io.StringIO(newline='');writer=csv.writer(output,lineterminator='\n');writer.writerows(rows+[added])
    normalized,count=normalize_centroid_csv(output.getvalue().encode())
    assert count==record['peak_count']+1
    assert parse(normalized).count(tuple(Decimal(v) for v in added))>=1


@pytest.mark.parametrize('mutation',['bad_header','negative_mz','negative_intensity','missing','nan','infinity','blank','extra_field','quote','nul'])
@pytest.mark.parametrize('record,raw',SAMPLES,ids=[r['massbank_accession'] for r,_ in SAMPLES])
def test_invalid_public_data_mutations_rejected_before_publication(tmp_path,record,raw,mutation):
    if mutation=='bad_header': changed=raw.replace(b'mz,intensity',b'mass,intensity',1)
    else:
        lines={'negative_mz':b'-1,1\n','negative_intensity':b'1,-1\n','missing':b'1,\n',
            'nan':b'nan,1\n','infinity':b'1,inf\n','blank':b'\n','extra_field':b'1,2,3\n','quote':b'"1,2\n','nul':b'1,\x00\n'}
        changed=raw+lines[mutation]
    source=tmp_path/'mutated.csv';source.write_bytes(changed)
    with pytest.raises(PilotError): import_centroid_csv(source,tmp_path/'runs',**metadata(record))
    assert not (tmp_path/'runs').exists()


@pytest.mark.parametrize('artifact',['source.csv','peaks.csv','manifest.json'])
@pytest.mark.parametrize('record,raw',SAMPLES,ids=[r['massbank_accession'] for r,_ in SAMPLES])
def test_tampering_against_pinned_digest_rejected(tmp_path,record,raw,artifact):
    source=tmp_path/'original.csv';source.write_bytes(raw)
    path=import_centroid_csv(source,tmp_path/'runs',**metadata(record))
    pin=hashlib.sha256(path.read_bytes()).hexdigest()
    target=path.parent/artifact
    if artifact=='manifest.json':
        data=json.loads(target.read_bytes());data['sample_id']='different-valid-sample';target.write_text(json.dumps(data))
    else: target.write_bytes(b'X'+target.read_bytes()[1:])
    with pytest.raises(PilotError): verify_centroid_bundle(path,expected_manifest_sha256=pin)
    assert source.read_bytes()==raw


@pytest.mark.parametrize('record,raw',SAMPLES,ids=[r['massbank_accession'] for r,_ in SAMPLES])
def test_approval_and_failed_write_boundaries(tmp_path,monkeypatch,record,raw):
    from virtual_lab.pilots import ms_workflow
    source=tmp_path/'original.csv';source.write_bytes(raw)
    fields=metadata(record);fields['approved_nonconfidential']=False
    with pytest.raises(PilotError): import_centroid_csv(source,tmp_path/'runs',**fields)
    fields['approved_nonconfidential']=True
    monkeypatch.setattr(ms_workflow,'write_private',lambda *a,**k: (_ for _ in ()).throw(OSError('simulated disk full')))
    with pytest.raises(OSError): import_centroid_csv(source,tmp_path/'runs',**fields)
    assert not list((tmp_path/'runs').iterdir())
    assert source.read_bytes()==raw
