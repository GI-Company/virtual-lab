"""Self-contained extension artifacts, checked independently of source file paths."""
import base64
import re
import uuid
from datetime import datetime
from virtual_lab.core.canonical import canonical_json

INSTRUMENTS = {'predictive_model': 'extension_predictor', 'instrument_import': 'extension_csv'}

def validate_result(value):
    from .models import predict_linear_bytes
    from .instruments import CSVInstrument
    if value.get('kind') == 'predictive_model':
        expected = predict_linear_bytes(value['model_manifest'].encode('utf-8'), value['inputs'])
    elif value.get('kind') == 'instrument_import':
        raw = base64.b64decode(value['raw_csv_base64'], validate=True)
        expected = CSVInstrument.from_bytes(value['raw_manifest'].encode('utf-8')).acquire_bytes(raw)
    else:
        raise ValueError('Unsupported notebook extension result.')
    # Retain the original fingerprint rather than rewriting historical provenance.
    if not re.fullmatch('[0-9a-f]{64}', value.get('adapter_sha256', '')):
        raise ValueError('Invalid adapter fingerprint.')
    expected['adapter_sha256'] = value['adapter_sha256']
    if canonical_json(value) != canonical_json(expected):
        raise ValueError('Extension payload disagrees with its retained source, status or output.')
    return expected


def validate_record(record):
    required = {'format', 'run_id', 'recorded_at', 'experiment_id', 'result'}
    if set(record) != required or record['format'] != 'vlab-notebook-extension-v1':
        raise ValueError('Unsupported notebook extension record.')
    uuid.UUID(record['run_id'])
    if not isinstance(record['experiment_id'], str) or not record['experiment_id']:
        raise ValueError('Missing extension experiment identity.')
    if datetime.fromisoformat(record['recorded_at']).tzinfo is None:
        raise ValueError('Timezone required for extension recording time.')
    validate_result(record['result'])
    return record


def result_csv(record, observation_id, artifact_sha256):
    """Export declared channels and statuses without promoting imported data."""
    import csv
    import io
    validate_record(record)
    value = record['result']
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=['observation_id', 'sample', 'channel', 'quantity',
        'role', 'value', 'unit', 'epistemic_state', 'artifact_sha256', 'source_sha256'])
    writer.writeheader()
    def write_row(row):
        # Spreadsheet applications can interpret source-controlled text as formulas.
        # Escape only text cells; numeric scientific values remain numeric.
        safe = {key: ("'" + item if isinstance(item, str) and item.lstrip().startswith(('=', '+', '-', '@')) else item)
                for key, item in row.items()}
        writer.writerow(safe)
    common = {'observation_id': observation_id, 'artifact_sha256': artifact_sha256,
        'source_sha256': value.get('source_sha256', value.get('model_sha256'))}
    if value['kind'] == 'predictive_model':
        for role, key, units, state in [('input','inputs','input_units','UNKNOWN'),
                                       ('output','outputs','output_units','PREDICTED')]:
            for name, number in value[key].items():
                write_row(dict(common, sample=0, channel=name, quantity=name, role=role,
                    value=number, unit=value[units][name], epistemic_state=state))
    else:
        for sample, row in enumerate(value['samples']):
            for channel in value['declarations']['channels']:
                write_row(dict(common, sample=sample, channel=channel['column'],
                    quantity=channel['quantity'], role=channel['role'], value=row[channel['column']],
                    unit=channel['unit'], epistemic_state='UNKNOWN'))
    return output.getvalue().encode('utf-8')
