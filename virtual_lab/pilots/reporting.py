"""Reproducible reports of software workflow checks, never scientific validation."""
from decimal import Decimal, localcontext
from pathlib import Path
from xml.sax.saxutils import escape
from virtual_lab.pilots.ms_workflow import read_verified_bundle, parse_centroids, canonical_decimal, json_bytes
from virtual_lab.pilots.schemas import MAX_REPORT_BYTES, PilotError
from virtual_lab.pilots.storage import checked_path, read_bounded


def spectrum_summary(raw):
    peaks = parse_centroids(raw, normalized=True)
    base = max(peaks, key=lambda p: p[1])
    with localcontext() as context:
        context.prec = 512
        total = sum((p[1] for p in peaks), Decimal(0))
    return {'peak_count':len(peaks), 'mz_min':canonical_decimal(min(p[0] for p in peaks)),
        'mz_max':canonical_decimal(max(p[0] for p in peaks)),
        'base_peak':{'mz':canonical_decimal(base[0]), 'intensity':canonical_decimal(base[1])},
        'total_intensity':canonical_decimal(total),
        'duplicate_mz_count':len(peaks)-len({p[0] for p in peaks}),
        'note':'Sum of imported centroid intensities; not instrument-reported total ion current. Numeric summaries are decimal strings.'}


def acceptance_checks(manifest, pin, events):
    def last(kind):
        return next((e['payload'] for e in reversed(events) if e['event_type']==kind), None)
    def result(key, label, status, detail):
        return {'id':key, 'label':label, 'status':status, 'detail':detail}
    rerun, alteration = last('MS_DATASET_REPROCESSED'), last('MS_INTEGRITY_CHALLENGE')
    registered, completed = last('MS_DATASET_REGISTERED'), last('MS_DATASET_COMPLETED')
    trace_fields = ('run_id','pilot_id','dataset_id','sample_id','instrument_id','source_sha256')
    trace = registered is not None and completed is not None
    trace_ok = trace and all(record.get(k)==manifest[k] for record in (registered,completed) for k in trace_fields)
    trace_ok = trace_ok and all(record.get('manifest_sha256')==pin for record in (registered,completed)) if trace else False
    return [
        result('import_validity','Import validity','PASS','Strict CSV schema, numeric bounds and normalized content verified.'),
        result('reproducibility','Reproducibility','NOT RUN' if rerun is None else 'PASS' if rerun.get('identical') is True and rerun.get('normalized_sha256')==manifest['normalized_sha256'] else 'FAIL',
               'No recorded rerun.' if rerun is None else 'Recorded rerun compared normalized bytes and digest.'),
        result('source_integrity','Source integrity','PASS','Source and normalized bytes match the recorded manifest digests.'),
        result('traceability','Traceability','NOT RUN' if not trace else 'PASS' if trace_ok else 'FAIL',
               'Registration and completion identifiers match the verified manifest.' if trace_ok else 'Complete matching local registration/completion evidence is unavailable.'),
        result('intentional_alteration','Intentional alteration','NOT RUN' if alteration is None else 'PASS' if alteration.get('detected') is True and alteration.get('original_unchanged') is True and alteration.get('manifest_sha256')==pin else 'FAIL',
               'No recorded challenge; no pass is assumed.' if alteration is None else 'An isolated source copy was changed; original research files were preserved.'),
    ]


def build_report(manifest_path, events=(), *, expected_manifest_sha256=None):
    manifest, contents, pin = read_verified_bundle(manifest_path, expected_manifest_sha256=expected_manifest_sha256)
    events = [e for e in events if e['payload'].get('run_id')==manifest['run_id']]
    reviews = [e for e in events if e['event_type']=='MS_DATASET_REVIEWED']
    reruns = [e for e in events if e['event_type']=='MS_DATASET_REPROCESSED']
    checks = acceptance_checks(manifest,pin,events)
    peaks = parse_centroids(contents['peaks.csv'], normalized=True)
    # The graph uses float coordinates only. Exact CSV/decimal metrics remain authoritative.
    return {'format':'virtuallab-ms-workflow-report', 'schema_version':2,
        'manifest':manifest, 'manifest_sha256':pin, 'summary':spectrum_summary(contents['peaks.csv']),
        'spectrum':{'mz':[float(p[0]) for p in peaks], 'intensity':[float(p[1]) for p in peaks],
                    'kind':'Imported centroid display; no analytical processing'},
        'acceptance_checks':checks,
        'workflow_check_status':'FAIL' if any(c['status']=='FAIL' for c in checks) else 'PASS' if all(c['status']=='PASS' for c in checks) else 'INCOMPLETE',
        'validation':{'status':'accepted','artifact_integrity':'verified','errors':[],'warnings':manifest['warnings']},
        'review_status':('approved' if reviews[-1]['payload']['approved'] else 'rejected') if reviews else 'not_reviewed',
        'reviews':reviews, 'reprocessing':reruns[-1]['payload'] if reruns else {'status':'not_run'},
        'provenance_events':events,
        'verification_scope':'Software workflow and byte integrity only. Evidence remains UNKNOWN. No instrument-origin, measurement-accuracy or biological validation.'}


def _event_summary(event):
    p,kind=event['payload'],event['event_type']
    if kind=='MS_DATASET_REGISTERED': return 'Registered', f"Dataset {p['dataset_id']}; sample {p['sample_id']}; instrument {p['instrument_id']}"
    if kind=='MS_DATASET_VALIDATED': return 'Validated', f"CSV accepted; {len(p.get('warnings',[]))} warning(s) recorded"
    if kind=='MS_DATASET_NORMALIZED': return 'Normalized', p.get('processing_version','Processing version unspecified')
    if kind=='MS_DATASET_COMPLETED': return 'Completed', 'Observation saved; evidence UNKNOWN'
    if kind=='MS_DATASET_REPROCESSED': return 'Reprocessed', 'Identical normalized bytes and digest' if p.get('identical') else 'Normalized output mismatch'
    if kind=='MS_INTEGRITY_CHALLENGE': return 'Alteration test', 'Altered copy rejected; original preserved' if p.get('detected') else 'FAIL: altered copy was not rejected'
    if kind=='MS_DATASET_REVIEWED': return 'Workflow review', ('Approved: ' if p.get('approved') else 'Rejected: ')+p.get('note','')[:160]
    if kind=='MS_DATASET_EXPORTED': return 'Exported', p.get('format','Report')+' report; digest recorded'
    return kind.replace('MS_','').replace('_',' ').capitalize(), 'Details retained in companion JSON'


def spectrum_drawing(report):
    from reportlab.graphics.shapes import Drawing, Line, String, Rect
    from reportlab.lib import colors
    drawing=Drawing(510,170)
    left,bottom,width,height=46,30,450,126
    x,y=report['spectrum']['mz'],report['spectrum']['intensity']
    xmin,xmax=min(x),max(x)
    span=xmax-xmin or max(abs(xmin)*.01,1)
    if xmax==xmin: xmin-=span/2
    ymax=max(y) or 1
    drawing.add(Rect(left,bottom,width,height,fillColor=colors.HexColor('#f4f8fc'),strokeColor=colors.HexColor('#cbd5e1')))
    # At most 1500 sticks in the PDF. Keep each display bin's strongest centroid.
    selected={}
    for mz,intensity in zip(x,y):
        bucket=min(1499,int((mz-xmin)/span*1500))
        if bucket not in selected or intensity>selected[bucket][1]: selected[bucket]=(mz,intensity)
    for mz,intensity in selected.values():
        px=left+(mz-xmin)/span*width
        drawing.add(Line(px,bottom,px,bottom+intensity/ymax*height,strokeColor=colors.HexColor('#0c789d'),strokeWidth=.7))
    for fraction in (0,.25,.5,.75,1):
        px=left+fraction*width
        drawing.add(String(px,bottom-13,f'{xmin+fraction*span:.6g}',fontName='Helvetica',fontSize=7,textAnchor='middle'))
    drawing.add(String(left+width/2,3,'Recorded m/z',fontName='Helvetica',fontSize=8,textAnchor='middle'))
    drawing.add(String(left-5,bottom+height-3,f'{ymax:.4g}',fontName='Helvetica',fontSize=7,textAnchor='end'))
    drawing.add(String(left-5,bottom,'0',fontName='Helvetica',fontSize=7,textAnchor='end'))
    drawing.add(String(left,bottom+height+7,'Intensity ('+(report['manifest']['intensity_units'] or 'unspecified units')+')',fontName='Helvetica',fontSize=7))
    return drawing


def pdf_bytes(report):
    import io
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
    from reportlab.lib.pagesizes import A4
    stream=io.BytesIO()
    doc=SimpleDocTemplate(stream,pagesize=A4,rightMargin=42,leftMargin=42,topMargin=36,bottomMargin=38,
        title='VirtualLab MS workflow report',author='Global Intent Company',invariant=1)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Value',fontName='Helvetica',fontSize=8,leading=10,wordWrap='CJK'))
    styles.add(ParagraphStyle(name='SmallValue',fontName='Helvetica',fontSize=7,leading=9,wordWrap='CJK'))
    def text(value, small=False): return Paragraph(escape(str(value if value is not None else 'unspecified')),styles['SmallValue' if small else 'Value'])
    def table(rows,widths,header=False):
        result=Table([[text(v,header) for v in row] for row in rows],colWidths=widths,repeatRows=1 if header else 0,hAlign='LEFT')
        result.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0) if header else (0,-1),colors.HexColor('#edf2f7')),
            ('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#cbd5e1')),('LEFTPADDING',(0,0),(-1,-1),6),
            ('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
        return result
    m,s=report['manifest'],report['summary']
    origin={'synthetic':'SYNTHETIC DEMONSTRATION | NOT INSTRUMENT DATA',
        'laboratory_supplied':'LABORATORY-SUPPLIED | ORIGIN UNVERIFIED',
        'public_reference':'PUBLIC EXPERIMENTAL REFERENCE | ORIGIN NOT INDEPENDENTLY VERIFIED',
        'unspecified':'DATA ORIGIN UNSPECIFIED | ORIGIN UNVERIFIED'}[m.get('data_origin','unspecified')]
    story=[Paragraph('VirtualLab / MS workflow report',styles['Title']),text(origin),
        text('Software workflow checks: '+report['workflow_check_status']+' | Review: '+report['review_status']+' | Evidence: UNKNOWN'),Spacer(1,8),
        spectrum_drawing(report),text('Centroid spectrum display. Dense spectra show the strongest centroid in each of 1,500 display bins; all entries remain in CSV/JSON.',True),Spacer(1,7),
        table([['Peak entries',s['peak_count'],'m/z range',s['mz_min']+' - '+s['mz_max']],
               ['Total centroid intensity',s['total_intensity'],'Repeated m/z entries',s['duplicate_mz_count']],
               ['Base peak m/z',s['base_peak']['mz'],'Base peak intensity',s['base_peak']['intensity']]], [130,125,130,125]),
        text('Summed centroid intensity is not instrument-reported total ion current. Metrics describe the submitted peak list only.',True),
        Paragraph('Software acceptance checks',styles['Heading2']),
        table([['Check','Outcome','Evidence / limitation']]+[[c['label'],c['status'],c['detail']] for c in report['acceptance_checks']],[115,58,337],True),
        Paragraph('Dataset and processing',styles['Heading2']),
        table([['Dataset',m['dataset_id'],'Sample',m['sample_id']],['Instrument',m['instrument_id'],'Operator',m['operator_id']],
            ['Acquired (UTC)',m['acquired_at_utc'],'Processed (UTC)',m['created_at_utc']],
            ['Processing',m['processing_version'],'Software',m['software_version']]], [83,172,83,172]),
        Spacer(1,6),text(report['verification_scope'],True),PageBreak(),
        Paragraph('Integrity and audit record',styles['Title']),text(origin),Spacer(1,8),
        table([['Pilot ID',m['pilot_id']],['Run ID',m['run_id']],['Source filename',m['source_filename']],
               ['Source SHA-256',m['source_sha256']],['Normalized SHA-256',m['normalized_sha256']],['Manifest SHA-256',report['manifest_sha256']]], [120,390]),
        Paragraph('Audit events',styles['Heading2'])]
    events=report['provenance_events']
    rows=[['Time (UTC)','Actor','Event','Outcome']]
    for event in events[-40:]:
        label,detail=_event_summary(event)
        rows.append([event['timestamp_utc'][:19].replace('T',' '),event['actor']['id'],label,detail])
    if not events: rows.append(['-','-','Not supplied','Standalone byte integrity only; no local lifecycle evidence.'])
    story += [table(rows,[85,75,85,265],True),Spacer(1,7),
        text(f'Showing the latest {min(len(events),40)} of {len(events)} events. Full event payloads and spectrum display coordinates are retained in the companion JSON report. The export receipt is recorded after publication and is supplied separately in the demo evidence packet.',True),
        Paragraph('Warnings and limitations',styles['Heading2'])]
    for warning in report['validation']['warnings']+m['limitations']:
        story.append(text('- '+warning,True))
    if m.get('source_reference'):
        reference=m['source_reference']
        story += [Paragraph('Source attribution',styles['Heading2']),
            text(reference['accession']+' | '+reference['license'],True),text(reference['attribution'],True),
            text(reference['url'],True),text(reference['notes'],True)]
    story += [Spacer(1,5),text('Data origin is a supplied declaration, not independent instrument attestation. Workflow approval does not validate measurement accuracy or biological conclusions.',True)]
    def footer(canvas,_doc):
        canvas.setFont('Helvetica',8)
        canvas.drawString(42,22,'VirtualLab | '+('Synthetic software demonstration' if m.get('data_origin')=='synthetic' else 'Workflow evaluation')+' | Evidence UNKNOWN')
        canvas.drawRightString(A4[0]-42,22,str(_doc.page))
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return stream.getvalue()


def render_report(report, suffix):
    raw=json_bytes(report) if suffix=='.json' else pdf_bytes(report)
    if len(raw)>MAX_REPORT_BYTES:
        raise PilotError('REPORT_SIZE_LIMIT','Report exceeds 16 MiB; export fewer audit events in a separately scoped report')
    return raw


def export_report(report, destination):
    from virtual_lab.gui.services.research_outputs import publish_new_file
    destination=checked_path(destination)
    if destination.suffix not in ('.json','.pdf'): raise PilotError('EXPORT_FORMAT','Choose a .json or .pdf filename')
    export_snapshot(report,destination)
    return destination


def export_snapshot(report,destination):
    """Publish a PDF with exact companion JSON, or a single JSON report."""
    from virtual_lab.gui.services.research_outputs import publish_new_file
    destination=checked_path(destination)
    if destination.suffix not in ('.json','.pdf'): raise PilotError('EXPORT_FORMAT','Choose a .json or .pdf filename')
    if any(ord(c)<32 for c in destination.name) or '\\' in destination.name:
        raise PilotError('EXPORT_FORMAT','Use a report filename without control characters or backslashes')
    paths=[destination.with_suffix('.json'),destination] if destination.suffix=='.pdf' else [destination]
    checksum_path=destination.with_suffix('.sha256')
    if any(path.exists() or path.is_symlink() for path in [*paths,checksum_path]):
        raise PilotError('EXPORT_EXISTS','Choose new filenames; existing reports are preserved')
    payloads=[render_report(report,path.suffix) for path in paths]
    from hashlib import sha256
    checksums=''.join(sha256(raw).hexdigest()+'  '+path.name+'\n' for path,raw in zip(paths,payloads)).encode('utf-8')
    paths.append(checksum_path)
    payloads.append(checksums)
    published=[]
    try:
        for path,raw in zip(paths,payloads):
            publish_new_file(path,raw)
            published.append(path)
    except BaseException:
        for path in published: path.unlink(missing_ok=True)
        raise
    return published


def verify_report_files(checksum_path):
    import hashlib,re
    checksum_path=checked_path(checksum_path)
    if checksum_path.suffix!='.sha256': raise PilotError('EXPORT_FORMAT','Select the exported .sha256 file')
    text=read_bounded(checksum_path,16384).decode('utf-8')
    rows=text.splitlines()
    if not 1<=len(rows)<=2: raise PilotError('CHECKSUM_SCHEMA','Expected one or two report checksums')
    names=set()
    for line in rows:
        match=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
        if not match: raise PilotError('CHECKSUM_SCHEMA','Malformed checksum line')
        digest,name=match.groups()
        if Path(name).name!=name or '\\' in name or any(ord(c)<32 for c in name) or Path(name).suffix not in ('.pdf','.json') or name in names:
            raise PilotError('CHECKSUM_SCHEMA','Unsafe or duplicate report filename')
        names.add(name)
        if hashlib.sha256(read_bounded(checksum_path.parent/name,MAX_REPORT_BYTES)).hexdigest()!=digest:
            raise PilotError('REPORT_INTEGRITY','Report checksum mismatch: '+name)
    return {'verified':True,'files':sorted(names),'scope':'Byte integrity against this checksum file; not publisher identity'}
