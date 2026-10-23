"""Real adapter execution against scratch inputs and a local text provider."""
import hashlib
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
from unittest.mock import patch
import numpy as np
import pytest
from virtual_lab.extensions.models import Expression, import_ode, predict_linear
from virtual_lab.extensions.instruments import CSVInstrument, save_extension_run
from virtual_lab.core.ledger import GenesisLedger, read_ledger_events

EXAMPLES=Path(__file__).parents[2]/'examples/extensions'

@pytest.mark.parametrize('text', ["__import__('os')", 'x.__class__', 'x[0]', 'x ** 10', '[x for x in y]', 'exp(x, x)', 'x + unknown'])
def test_expression_rejects_code(text):
    with pytest.raises((ValueError,SyntaxError)): Expression(text, {'x'})


def test_imported_ode_runs_shared_solver_with_pinned_source(tmp_path,monkeypatch):
    import virtual_lab.models.registry as registry
    registry.models();monkeypatch.setattr(registry,'_MODELS',dict(registry._MODELS))
    source=tmp_path/'source.json';source.write_bytes((EXAMPLES/'decay.json').read_bytes())
    spec=import_ode(source,tmp_path/'pinned')
    source.write_text('{}')
    from virtual_lab.gui.services.simulation_runner import RunConfig,run_simulation
    result=run_simulation(RunConfig(model_id=spec.id,members=4,duration_h=2,variation=0))
    np.testing.assert_allclose(result['final_state'],np.full((4,1),np.exp(-.4)),rtol=1e-8)
    assert result['numerical_check']['status']=='PASSED'
    assert hashlib.sha256(spec.source_files[0].read_bytes()).hexdigest() in result['source_hashes'].values()


def test_predict_and_acquire_preserve_status_and_payload(tmp_path):
    result=predict_linear(EXAMPLES/'linear.json',{'concentration':3})
    assert result['outputs']=={'response':7} and result['epistemic_state']=='PREDICTED'
    imported=CSVInstrument(EXAMPLES/'instrument.json').acquire(EXAMPLES/'signal.csv')
    assert len(imported['samples'])==3 and imported['epistemic_state']=='UNKNOWN'
    assert imported['source_sha256']==hashlib.sha256((EXAMPLES/'signal.csv').read_bytes()).hexdigest()
    ledger=GenesisLedger(str(tmp_path/'genesis.db'))
    for output in (result,imported):
        path=save_extension_run(output,tmp_path/'results',ledger)
        assert path.stem==hashlib.sha256(path.read_bytes()).hexdigest()
    ledger.conn.close()
    assert [e.payload['epistemic_state'] for e in read_ledger_events(tmp_path/'genesis.db')[1:]]==['PREDICTED','UNKNOWN']


def test_bad_csv_and_unknown_units_rejected(tmp_path):
    source=tmp_path/'bad.csv';source.write_text('time,signal\n0,nan\n')
    with pytest.raises(ValueError,match='Nonfinite'): CSVInstrument(EXAMPLES/'instrument.json').acquire(source)
    manifest=json.loads((EXAMPLES/'linear.json').read_text());manifest['input_units']=['fake_unknown_unit']
    path=tmp_path/'bad.json';path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='Unknown declared unit'): predict_linear(path,{'concentration':1})


def test_assistant_explicit_opt_in_redaction_and_real_http(tmp_path):
    from virtual_lab.extensions.assistant import AssistantEndpoint
    requests=[]
    class Provider(BaseHTTPRequestHandler):
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(data)
            self.send_response(200);self.end_headers()
            self.wfile.write(b'{"choices":[{"message":{"content":"Review your assumptions."}}]}')
        def log_message(self,*args): pass
    server=HTTPServer(('127.0.0.1',0),Provider)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        endpoint=AssistantEndpoint(f'http://127.0.0.1:{server.server_port}/v1/chat/completions','test-model','test-secret')
        with pytest.raises(ValueError,match='opt-in'): endpoint.critique('Review')
        assert not requests
        output=endpoint.critique('Review',allow_network=True)
        assert output['epistemic_state']=='INFERRED' and not output['authoritative']
        assert 'tools' not in requests[0] and 'test-secret' not in json.dumps(output)
        ledger=GenesisLedger(str(tmp_path/'genesis.db'))
        path=save_extension_run(output,tmp_path/'results',ledger);ledger.conn.close()
        assert 'test-secret' not in path.read_text()
    finally:
        server.shutdown();server.server_close();thread.join()
    with pytest.raises(ValueError): AssistantEndpoint('http://example.com/chat','test')
    with pytest.raises(ValueError): AssistantEndpoint('https://user:secret@example.com/chat','test')


def test_unpaired_gateway_drops_all_channels(qtbot,tmp_path):
    from virtual_lab.instruments.transport.gateway import InstrumentGateway
    from tests.instruments.test_bugfixes import MockSocket
    ledger=GenesisLedger(str(tmp_path/'g.db'))
    with patch('virtual_lab.instruments.transport.gateway.QWebSocketServer'):
        gateway=InstrumentGateway(ledger)
        for channel,method,payload in [('sensors',gateway._on_message,'{}'),('control',gateway._on_control_message,'{}'),('camera',gateway._on_binary_message,b'not-a-frame')]:
            socket=MockSocket('/'+channel)
            gateway.server.nextPendingConnection.return_value=socket
            gateway._on_new_connection();conn_id=list(gateway.registry.connections)[-1]
            method(socket,conn_id,payload)
            assert not gateway.registry.get_connection(conn_id).bound_device_id
        assert not gateway._authenticated_connections
    ledger.conn.close()


def test_typed_camera_controls_roundtrip_without_broadcast(qtbot,tmp_path):
    from virtual_lab.instruments.transport.gateway import InstrumentGateway
    from virtual_lab.gui.instruments.control_panel import ControlPanel
    from virtual_lab.instruments.transport.protocol_v1 import CameraCapabilities,CameraControlResult,CameraControlRequest
    from virtual_lab.instruments.control import ControlStateStatus
    from tests.instruments.test_bugfixes import MockSocket
    from unittest.mock import Mock
    ledger=GenesisLedger(str(tmp_path/'g.db'))
    gateway=InstrumentGateway(ledger)
    panel=ControlPanel(gateway,ledger=ledger);qtbot.addWidget(panel)
    caps=CameraCapabilities(device_id='paired',camera_stream_key={'camera_id':'0'},manual_focus_supported=True,minimum_focus_distance_diopters=4)
    panel._on_capabilities(caps)
    assert panel.capabilities.minimum_focus_distance==4
    socket=MockSocket('/control');socket.sendTextMessage=Mock()
    with patch.object(gateway.server,'nextPendingConnection',return_value=socket): gateway._on_new_connection()
    connection=list(gateway.registry.connections)[-1]
    assert gateway.send_control_message({'device_id':'paired','message_type':'TEST'}) is False
    gateway.pair_device('paired','t'*32)
    gateway._try_parse_hello('/control',connection,json.dumps({'message_type':'CHANNEL_HELLO',
        'channel':'control','device_id':'paired','pairing_token':'t'*32}))
    panel._send_request('FOCUS',2)
    msg=json.loads(socket.sendTextMessage.call_args[0][0]);CameraControlRequest.model_validate(msg)
    assert msg['requested_parameters']=={'focus_distance_diopters':2}
    panel._on_response(CameraControlResult(request_id=msg['request_id'],device_id='paired',overall_status='APPLIED',
        parameter_results={'focus_distance_diopters':{'requested':2,'applied':2,'status':'APPLIED'}}))
    assert panel.requests[msg['request_id']].status==ControlStateStatus.APPLIED
    assert ledger.get_head().event_type=='INSTRUMENT_CAMERA_CONTROL_APPLIED'
    socket.sendTextMessage.reset_mock()
    assert gateway.send_control_message({'message_type':'TEST'}) is False
    socket.sendTextMessage.assert_not_called()
    gateway.stop();ledger.conn.close()
