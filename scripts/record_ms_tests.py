"""Capture a real Qt application session and live pytest output with automated UI actions.

Requires a native desktop and an ffmpeg executable. File-picker return paths are
provided programmatically; form entry and workflow buttons use actual Qt events.
No instrument control or AI provider is loaded.
"""
import argparse
import hashlib
import importlib.abc
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples-dir',type=Path,required=True)
    parser.add_argument('--samples-zip',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--ffmpeg',type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    sources=args.samples_dir.resolve()
    records=json.loads((sources/'verified-source-records.json').read_bytes())
    os.environ['VIRTUALLAB_DATA_DIR']=str(output/'workspace')
    class NoAI(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,*_):
            if fullname.startswith(('virtual_lab.ai','google','groq')): raise AssertionError('Unexpected AI import')
    sys.meta_path.insert(0,NoAI())
    def deny(*_,**__): raise AssertionError('Unexpected network access during recording')
    socket.socket.connect=deny;socket.socket.bind=deny
    from PySide6.QtCore import Qt,QTimer,QPoint,QProcess,QProcessEnvironment
    from PySide6.QtGui import QImage,QPainter,QColor,QPen
    from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QLabel,QTabWidget,QPlainTextEdit,QPushButton,QScrollArea,QFileDialog
    from PySide6.QtTest import QTest
    from virtual_lab.pilots.desktop import MSPilotWindow
    app=QApplication([]);app.setQuitOnLastWindowClosed(False)
    width,height,fps=1400,800,12
    cast=QWidget();cast.setWindowTitle('VirtualLab | Public MS workflow test recording');cast.setFixedSize(width,height)
    cast.setStyleSheet('background:#101b2b;color:#edf5ff;')
    layout=QVBoxLayout(cast);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
    title=QLabel('VirtualLab | Public-reference MS workflow tests')
    title.setStyleSheet('font-size:21px;font-weight:bold;color:#74d5ff;padding:8px 15px 0px;')
    caption=QLabel('Actual application session; automated Qt interactions and live test output.')
    caption.setStyleSheet('font-size:14px;padding:3px 15px 8px;');caption.setWordWrap(True)
    layout.addWidget(title);layout.addWidget(caption)
    screens=QTabWidget();layout.addWidget(screens,1)
    app_slot=QWidget();app_layout=QVBoxLayout(app_slot);app_layout.setContentsMargins(0,0,0,0)
    window=MSPilotWindow();window.setParent(app_slot,Qt.Widget);app_layout.addWidget(window);window.show()
    screens.addTab(app_slot,'Live VirtualLab')
    console=QPlainTextEdit();console.setReadOnly(True);console.setStyleSheet('font-family:Menlo;font-size:12px;background:#09131f;color:#d6eef9;')
    screens.addTab(console,'Live automated tests')
    footer=QLabel('PUBLIC REFERENCE DATA | Small-molecule MS2 peak lists | Workflow checks only | Evidence UNKNOWN | AI / instruments off')
    footer.setStyleSheet('font-size:12px;padding:6px;color:#ffda9b;');footer.setAlignment(Qt.AlignCenter);layout.addWidget(footer)
    cast.show();cast.raise_();cast.activateWindow();QTest.qWait(700)
    log=(output/'encoder.log').open('wb')
    encoder=subprocess.Popen([str(args.ffmpeg),'-n','-loglevel','warning','-f','rawvideo','-pixel_format','rgb24',
        '-video_size',f'{width}x{height}','-framerate',str(fps),'-i','-','-an','-c:v','libx264','-preset','veryfast','-crf','20',
        '-pix_fmt','yuv420p','-movflags','+faststart',str(output/'VirtualLab-Public-MS-Test-Recording.mp4')],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
    started=time.monotonic();frames=0;chapters=[];pointer=QPoint(-1,-1);clicked_until=0
    def capture():
        nonlocal frames
        image=cast.grab().toImage().scaled(width,height,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
        image.setDevicePixelRatio(1)
        painter=QPainter(image)
        if pointer.x()>=0:
            painter.setPen(QPen(QColor('#111827'),2));painter.setBrush(QColor('#f8fafc'));painter.drawEllipse(pointer,4,4)
            if time.monotonic()<clicked_until:
                painter.setPen(QPen(QColor('#fbbf24'),3));painter.setBrush(Qt.NoBrush);painter.drawEllipse(pointer,15,15)
        painter.end();image=image.convertToFormat(QImage.Format_RGB888)
        data=bytes(image.constBits());target=int((time.monotonic()-started)*fps)+1
        for _ in range(max(1,target-frames)): encoder.stdin.write(data);frames+=1
    timer=QTimer();timer.timeout.connect(capture);timer.start(round(1000/fps));capture()
    def pause(seconds=.5): QTest.qWait(round(seconds*1000))
    def chapter(name,detail):
        title.setText(name);caption.setText(detail)
        chapters.append({'seconds':round(frames/fps,2),'title':name,'caption':detail})
        print(json.dumps(chapters[-1]),flush=True);pause(1.5)
    def reveal(widget):
        parent=widget.parentWidget()
        while parent:
            if isinstance(parent,QScrollArea): parent.ensureWidgetVisible(widget,12,15)
            parent=parent.parentWidget()
        pause(.1)
    def click(widget,point=None,wait=.45):
        nonlocal pointer,clicked_until
        reveal(widget);point=point or widget.rect().center();pointer=widget.mapTo(cast,point);clicked_until=time.monotonic()+.5
        QTest.mouseClick(widget,Qt.LeftButton,Qt.NoModifier,point);pause(wait)
    def fill(widget,value):
        click(widget,wait=.1);QTest.keyClick(widget,Qt.Key_A,Qt.ControlModifier);QTest.keyClicks(widget,str(value));pause(.12)
        assert widget.text()==str(value),(widget.text(),value)
    def button(root,label):
        matches=[b for b in root.findChildren(QPushButton) if b.text()==label]
        assert len(matches)==1,(label,len(matches));return matches[0]
    def tab(tabs,index): click(tabs.tabBar(),tabs.tabBar().tabRect(index).center())
    exit_code=1
    try:
        chapter('1 / Automated workflow and security tests','The console streams real pytest output. The supplied public spectra stay outside Git.')
        tab(screens,1)
        process=QProcess();process.setProcessChannelMode(QProcess.MergedChannels)
        env=QProcessEnvironment.systemEnvironment();env.insert('QT_QPA_PLATFORM','offscreen');env.insert('VIRTUALLAB_PUBLIC_MS_ZIP',str(args.samples_zip.resolve()))
        process.setProcessEnvironment(env)
        repo=Path(__file__).resolve().parents[1];process.setWorkingDirectory(str(repo))
        output_log=[]
        def read_tests():
            text=bytes(process.readAllStandardOutput()).decode(errors='replace');output_log.append(text);console.insertPlainText(text);console.ensureCursorVisible()
        process.readyReadStandardOutput.connect(read_tests)
        process.start(sys.executable,['-m','pytest','tests/pilots','tests/test_pilot_release_gates.py','tests/gui/test_ms_pilot_workspace.py','-v','--color=no','--junitxml='+str(output/'recorded-test-results.xml')])
        deadline=time.monotonic()+60
        while process.state()!=QProcess.NotRunning:
            if time.monotonic()>deadline: process.kill();raise RuntimeError('Recorded tests timed out')
            pause(.1)
        read_tests();(output/'recorded-tests.log').write_text(''.join(output_log));assert process.exitCode()==0,console.toPlainText()[-4000:]
        pause(3)
        tab(screens,0)
        chapter('2 / Create the local project and study','This is a local project with three public reference datasets; no multi-user server is claimed.')
        projects=window.projects
        fill(projects.project_name,'Public MassBank workflow tests');click(button(projects,'Create project'))
        fill(projects.experiment_name,'Public MS2 CSV software checks')
        fill(projects.question,'Can public peak lists be preserved, traced, rerun and exported with verifiable hashes?')
        click(button(projects,'Create and open experiment'));assert window.workspace.active_experiment is not None
        tab(window.tabs,1);panel=window.ms_pilot
        artifacts=[]
        for index,record in enumerate(records):
            chapter(f"{3+index} / {record['massbank_accession']} | {record['peak_count']} peak entries",
                'Public experimental reference peak list. Import, integrity, rerun and review checks do not establish scientific accuracy.')
            tab(panel.tabs,0)
            for key,value in {'source':str(sources/record['filename']),'pilot_id':'public-ms-reference-tests','dataset_id':record['massbank_accession'],
                'sample_id':'reference-'+record['massbank_accession'],'instrument_id':'MassBank-claimed-QExactive','operator_id':'workflow-tester'}.items(): fill(panel.fields[key],value)
            panel.data_origin.setFocus();QTest.keyClick(panel.data_origin,Qt.Key_Home)
            for _ in range(panel.data_origin.findData('public_reference')): QTest.keyClick(panel.data_origin,Qt.Key_Down)
            pause(.3);assert panel.data_origin.currentData()=='public_reference'
            if not panel.source_group.isChecked(): click(panel.source_group,QPoint(12,12))
            values={'accession':record['massbank_accession'],'url':record['source_url'],'license':record['license']+' (version unspecified in source)',
                'attribution':record['authors'],'notes':'Adapted PK$PEAK m/z and intensity columns only; relative intensity and other metadata omitted. Public processed MS2 peak list; not original vendor data.'}
            for key,value in values.items(): fill(panel.source_fields[key],value)
            if not panel.approval.isChecked(): click(panel.approval,QPoint(8,panel.approval.height()//2))
            click(panel.validate_button);assert panel.validated is not None,panel.status.text();pause(2)
            tab(panel.tabs,0);click(panel.import_button);assert panel.selected_run is not None,panel.status.text()
            run_id=panel.selected_run
            tab(panel.tabs,1);pause(2)
            click(button(panel,'Verify integrity'));assert 'verified' in panel.status.text().lower(),panel.status.text()
            click(button(panel,'Compare repeat processing'));assert 'identical' in panel.status.text(),panel.status.text()
            click(button(panel,'Test alteration detection'));assert 'PASS' in panel.status.text(),panel.status.text();pause(1)
            tab(panel.tabs,2);pause(1.5)
            tab(panel.tabs,3);fill(panel.reviewer,'workflow-reviewer');fill(panel.review_note,'Public reference software checks approved; evidence remains UNKNOWN.')
            click(button(panel,'Record workflow review'));assert 'UNKNOWN' in panel.status.text()
            target=output/(record['massbank_accession']+'-workflow-report.pdf')
            original_save=QFileDialog.getSaveFileName;QFileDialog.getSaveFileName=lambda *a,**k:(str(target),'PDF report (*.pdf)')
            try: click(button(panel,'Export JSON / PDF report'))
            finally: QFileDialog.getSaveFileName=original_save
            assert target.is_file(),panel.status.text()
            receipt=panel.service.events(run_id)[-1];(output/(target.stem+'-export-receipt.json')).write_text(json.dumps(receipt,indent=2)+'\n')
            chosen=target.with_suffix('.sha256');original_open=QFileDialog.getOpenFileName;QFileDialog.getOpenFileName=lambda *a,**k:(str(chosen),'SHA-256 checksums (*.sha256)')
            try: click(button(panel,'Verify exported PDF / JSON checksums'))
            finally: QFileDialog.getOpenFileName=original_open
            assert 'PASS' in panel.status.text(),panel.status.text();pause(1.5)
            tab(panel.tabs,1)
            evidence=output/'evidence'/record['massbank_accession'];evidence.mkdir(parents=True)
            source_manifest=panel.service.manifest_path(run_id)
            for name in ('source.csv','peaks.csv','manifest.json'): shutil.copyfile(source_manifest.parent/name,evidence/name)
            panel.grab().save(str(output/(record['massbank_accession']+'-spectrum.png')))
            artifacts.append({'accession':record['massbank_accession'],'run_id':run_id,'peak_count':record['peak_count'],'report':target.name})
        chapter('6 / Verify a changed report is rejected','An exported copy is deliberately changed. Its checksum verification must fail; original reports stay intact.')
        altered=output/'intentional-alteration-copy';altered.mkdir()
        for suffix in ('.pdf','.json','.sha256'): shutil.copyfile(target.with_suffix(suffix),altered/target.with_suffix(suffix).name)
        changed=altered/target.name;changed.write_bytes(changed.read_bytes()+b'changed report copy')
        chosen=altered/target.with_suffix('.sha256').name
        original_open=QFileDialog.getOpenFileName;QFileDialog.getOpenFileName=lambda *a,**k:(str(chosen),'SHA-256 checksums (*.sha256)')
        try: click(button(panel,'Verify exported PDF / JSON checksums'))
        finally: QFileDialog.getOpenFileName=original_open
        assert 'REPORT_INTEGRITY' in panel.status.text(),panel.status.text();pause(3)
        chosen=target.with_suffix('.sha256');QFileDialog.getOpenFileName=lambda *a,**k:(str(chosen),'SHA-256 checksums (*.sha256)')
        try: click(button(panel,'Verify exported PDF / JSON checksums'))
        finally: QFileDialog.getOpenFileName=original_open
        assert 'PASS' in panel.status.text();pause(1)
        chapter('7 / Export the complete local study','The study package includes all three preserved sources, normalized peaks and manifests. Separate reports retain review history and checksums.')
        tab(window.tabs,0);fill(projects.package_path,str(output/'public-ms-reference-study.vlab-study'));click(button(projects,'Export study package'))
        assert (output/'public-ms-reference-study.vlab-study').is_file(),projects.status.text()
        tab(window.tabs,1);tab(panel.tabs,1)
        chapter('Completed / Public data workflow tests','Three public reference datasets exercised. Reports include plots, pass/fail checks, attribution, JSON and detached SHA-256 checksums. Evidence remains UNKNOWN.')
        pause(4);cast.grab().save(str(output/'recording-preview.png'))
        (output/'recording-result.json').write_text(json.dumps({'status':'passed','datasets':artifacts,'data_origin':'public_reference','network':'blocked','AI':'absent'},indent=2)+'\n')
        exit_code=0
    finally:
        timer.stop();capture();encoder.stdin.close();encoder.wait(timeout=30);log.close()
        (output/'chapters.json').write_text(json.dumps(chapters,indent=2)+'\n')
        (output/'video-provenance.json').write_text(json.dumps({'capture':'Actual native Qt widget rendering at 12 fps; no generated application screenshots',
            'interaction':'Automated Qt mouse/key events; save/open file-picker return paths supplied programmatically',
            'frames':frames,'duration_seconds':frames/fps,'outcome':'passed' if exit_code==0 else 'failed',
            'tests':'Actual pytest subprocess output; full log and JUnit included','audio':'none; on-screen captions'},indent=2)+'\n')
        window.close();cast.close()
        if encoder.returncode!=0: raise RuntimeError('Video encoding failed')
    return exit_code


if __name__=='__main__': raise SystemExit(main())
