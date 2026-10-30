"""Reproducible workflow reports. Descriptive peak-list metrics only."""
from decimal import Decimal, localcontext
from pathlib import Path
from xml.sax.saxutils import escape
from virtual_lab.pilots.ms_workflow import (read_verified_bundle,
    parse_centroids, canonical_decimal, json_bytes, _sha256)
from virtual_lab.pilots.schemas import MAX_SOURCE_BYTES
from virtual_lab.pilots.storage import checked_path, read_bounded


def spectrum_summary(raw):
    peaks = parse_centroids(raw)
    base = max(peaks, key=lambda p: p[1])
    with localcontext() as context:
        context.prec = 512  # 128 input digits + bounded exponents + 100000-row aggregate
        total = sum((p[1] for p in peaks), Decimal(0))
    return {'peak_count': len(peaks), 'mz_min': canonical_decimal(min(p[0] for p in peaks)),
        'mz_max': canonical_decimal(max(p[0] for p in peaks)),
        'base_peak': {'mz': canonical_decimal(base[0]), 'intensity': canonical_decimal(base[1])},
        'total_intensity': canonical_decimal(total),
        'duplicate_mz_count': len(peaks) - len({p[0] for p in peaks}),
        'note': 'Sum of imported centroid intensities; not instrument-reported total ion current. Numeric summaries are decimal strings.'}


def build_report(manifest_path, events=(), *, expected_manifest_sha256=None):
    manifest, contents, manifest_sha256 = read_verified_bundle(manifest_path, expected_manifest_sha256=expected_manifest_sha256)
    events = [e for e in events if e['payload'].get('run_id') == manifest['run_id']]
    reviews = [e for e in events if e['event_type'] == 'MS_DATASET_REVIEWED']
    reruns = [e for e in events if e['event_type'] == 'MS_DATASET_REPROCESSED']
    return {'format': 'virtuallab-ms-workflow-report', 'schema_version': 1,
        'manifest': manifest,
        'manifest_sha256': manifest_sha256,
        'summary': spectrum_summary(contents['peaks.csv']),
        'validation': {'status': 'accepted', 'artifact_integrity': 'verified', 'errors': [], 'warnings': manifest['warnings']},
        'review_status': ('approved' if reviews[-1]['payload']['approved'] else 'rejected') if reviews else 'not_reviewed',
        'reviews': reviews, 'reprocessing': reruns[-1]['payload'] if reruns else {'status': 'not_run'},
        'provenance_events': events,
        'verification_scope': 'Local workflow and byte integrity only. UNKNOWN evidence; no measurement or instrument-origin validation.'}


def pdf_bytes(report):
    import io
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.pagesizes import A4
    stream = io.BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=42,
                           title='VirtualLab MS workflow report', author='Global Intent Company', invariant=1)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Value', fontName='Helvetica', fontSize=8, leading=11, wordWrap='CJK'))
    story = [Paragraph('VirtualLab / MS workflow report', styles['Title']),
             Paragraph('Nonconfidential pilot | Workflow validation | UNKNOWN evidence', styles['Normal']), Spacer(1, 12)]
    def text(value):
        return Paragraph(escape(str(value if value is not None else 'unspecified')), styles['Value'])
    def section(title, rows):
        story.append(Paragraph(title, styles['Heading2']))
        table = Table([[text(k.replace('_', ' ').capitalize()), text(v)] for k, v in rows], colWidths=[145, 365], hAlign='LEFT')
        table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'), ('BACKGROUND',(0,0),(0,-1),colors.HexColor('#edf2f7')),
            ('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#ccd5df')), ('LEFTPADDING',(0,0),(-1,-1),7),
            ('TOPPADDING',(0,0),(-1,-1),5), ('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        story.append(table)
    m, s = report['manifest'], report['summary']
    section('Dataset and acquisition', [(k,m[k]) for k in ('pilot_id','dataset_id','run_id','sample_id','instrument_id','operator_id',
        'acquired_at_utc','created_at_utc','source_filename','mz_units','intensity_units')])
    section('Processing and descriptive summary', [(k,m[k]) for k in ('processing_version','software_version','import_status','epistemic_state')]
        + [(k,s[k]) for k in ('peak_count','mz_min','mz_max','base_peak','total_intensity','duplicate_mz_count')])
    story.append(Paragraph(escape(s['note']), styles['Value']))
    section('Integrity and reproducibility', [(k,report.get(k,m.get(k))) for k in
        ('source_sha256','normalized_sha256','manifest_sha256','review_status','reprocessing')])
    section('Validation, warnings and limitations', [('validation', report['validation'])] + [('limitation',x) for x in m['limitations']])
    story.append(Paragraph('Evidence and review history', styles['Heading2']))
    for event in report['provenance_events']:
        story.append(Paragraph(escape(f"{event['timestamp_utc']} | {event['event_type']} | {event['actor']['id']}"), styles['Value']))
        story.append(Paragraph(escape(str(event['payload'])), styles['Value']))
        story.append(Spacer(1, 5))
    if not report['provenance_events']:
        story.append(Paragraph('No lifecycle events supplied. Standalone file integrity only.', styles['Value']))
    story.append(Spacer(1, 12))
    story.append(Paragraph(escape(report['verification_scope']), styles['Value']))
    def footer(canvas, _doc):
        canvas.setFont('Helvetica', 8)
        canvas.drawString(42, 24, 'VirtualLab | MS workflow evaluation | No scientific validity claim')
        canvas.drawRightString(A4[0]-42, 24, str(_doc.page))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()


def export_report(report, destination):
    from virtual_lab.gui.services.research_outputs import publish_new_file
    destination = checked_path(destination)
    if destination.suffix not in ('.json', '.pdf'):
        raise ValueError('Choose a .json or .pdf report filename')
    raw = json_bytes(report) if destination.suffix == '.json' else pdf_bytes(report)
    return publish_new_file(destination, raw)
