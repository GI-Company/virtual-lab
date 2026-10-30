"""Smoke-test a non-editable pilot wheel with AI absent and network blocked."""
import argparse
import importlib.abc
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import sysconfig


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if importlib.util.find_spec('google') is not None:
        raise AssertionError('Expected an environment without optional AI packages')
    class NoAI(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,*_):
            if fullname.startswith(('google','groq','virtual_lab.ai')):
                raise AssertionError('Unexpected AI import: '+fullname)
    sys.meta_path.insert(0,NoAI())
    def deny(*_,**__): raise AssertionError('Unexpected network access')
    socket.socket.connect=deny
    socket.socket.bind=deny
    from PySide6.QtWidgets import QApplication
    from virtual_lab.pilots.desktop import MSPilotWindow
    import virtual_lab.pilots.desktop as desktop
    from virtual_lab.version import __version__
    if not Path(desktop.__file__).resolve().is_relative_to(Path(sysconfig.get_paths()['purelib']).resolve()):
        raise AssertionError('Smoke test imported source instead of the installed wheel')
    app=QApplication([])
    window=MSPilotWindow()
    try:
        study=window.projects.service
        project=study.create_project('Installed synthetic pilot')
        experiment=study.create_experiment(project,'Offline CSV workflow','Can the installed wheel reproduce a synthetic workflow?')
        root=Path(os.environ['VIRTUALLAB_DATA_DIR'])
        source=root/'synthetic.csv';source.write_text('mz,intensity\n100,1\n101,3\n')
        service=window.ms_pilot.service
        obs=service.import_csv(source,experiment_id=experiment,data_origin='synthetic',sample_id='synthetic-s',instrument_id='synthetic-i',operator_id='tester',approved_nonconfidential=True)
        assert service.reprocess(obs.session_id)['identical']
        assert service.test_alteration(obs.session_id)['detected']
        service.review(obs.session_id,reviewer='tester',approved=True,note='Synthetic software checks')
        service.export_report(obs.session_id,root/'smoke-report.pdf')
        report=json.loads((root/'smoke-report.json').read_bytes())
        assert report['workflow_check_status']=='PASS' and report['manifest']['epistemic_state']=='UNKNOWN'
        receipt={'status':'passed','version':__version__,'network':'blocked','AI':'absent',
            'installed_package':desktop.__file__,'workflow_checks':report['acceptance_checks']}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(receipt,indent=2)+'\n')
        print('Installed wheel workflow passed with AI absent and sockets blocked')
    finally:
        window.close()


if __name__=='__main__': main()
