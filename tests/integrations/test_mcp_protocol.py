"""Real SDK handshake and stdio calls. No ChatGPT account or cloud API is used."""
import asyncio
from pathlib import Path
import sys
import pytest

pytest.importorskip('mcp', reason='Optional MCP SDK is not installed')
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from tests.integrations.test_mcp_snapshot import snapshot, allow, fingerprint


def test_real_stdio_client_contract_and_revocation(snapshot):
    reader,repo,run,service,root=snapshot
    before=fingerprint(root/'snapshot')
    events=len(service.events(run))
    args=['-m','virtual_lab.integrations.mcp.server','--snapshot',str(reader.root),
          '--snapshot-sha256',reader.catalog_sha256,'--settings-root',str(repo.root)]
    async def exercise():
        parameters=StdioServerParameters(command=sys.executable,args=args,
            cwd=str(Path(__file__).resolve().parents[2]))
        async with stdio_client(parameters) as (receive,send):
            async with ClientSession(receive,send) as session:
                initialized=await session.initialize()
                assert initialized.serverInfo.name=='VirtualLab MS snapshot'
                assert initialized.serverInfo.version=='0.1.0'
                tools=(await session.list_tools()).tools
                assert {t.name for t in tools}=={'list_projects','get_experiment','get_spectrum',
                    'verify_dataset','get_report','get_intent_status'}
                for tool in tools:
                    assert tool.annotations.readOnlyHint is True
                    assert tool.annotations.destructiveHint is False
                    assert tool.annotations.openWorldHint is False
                    assert tool.outputSchema['properties']['scope']
                response=await session.call_tool('list_projects',{})
                assert response.structuredContent['data']['projects']==[]
                allow(repo,reports=True)
                projects=(await session.call_tool('list_projects',{})).structuredContent['data']['projects']
                assert projects[0]['id']=='p'
                base={'project_id':'p','experiment_id':'e','dataset_id':run}
                metadata=await session.call_tool('get_experiment',{'project_id':'p','experiment_id':'e'})
                assert metadata.structuredContent['data']['dataset_ids']==[run]
                checked=await session.call_tool('verify_dataset',base)
                assert checked.structuredContent['data']['integrity']=='PASS'
                denied=await session.call_tool('get_spectrum',base)
                assert denied.isError
                allow(repo,spectrum=True,reports=True)
                spectrum=await session.call_tool('get_spectrum',dict(base,limit=2))
                assert len(spectrum.structuredContent['data']['points'])==2
                report=await session.call_tool('get_report',base)
                assert report.structuredContent['data']['epistemic_state']=='UNKNOWN'
                assert 'spectrum' not in report.structuredContent['data']
                intent=await session.call_tool('get_intent_status',{'project_id':'p','experiment_id':'e'})
                assert intent.structuredContent['data']['available'] is False
                bad=await session.call_tool('get_spectrum',dict(base,limit=501))
                assert bad.isError
                cross=await session.call_tool('get_report',dict(base,project_id='other'))
                assert cross.isError and str(root) not in str(cross)
                data=repo.load().model_dump(); data['mcp_enabled']=False; repo.save(data)
                denied=await session.call_tool('get_report',base)
                assert denied.isError
                assert (await session.call_tool('list_projects',{})).structuredContent['data']['projects']==[]
    asyncio.run(exercise())
    assert fingerprint(root/'snapshot')==before
    assert len(service.events(run))==events
