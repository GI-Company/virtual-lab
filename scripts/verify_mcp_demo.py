"""Real local MCP protocol demonstration; temporarily enable only isolated demo sharing."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo',type=Path,required=True)
    args=parser.parse_args()
    if not __debug__:
        parser.error('Verification requires Python assertions to be enabled')
    root=args.demo.resolve()
    from virtual_lab.settings import SettingsRepository
    from virtual_lab.pilots.ms_workflow import json_bytes
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    metadata=json.loads((root/'demo.json').read_text())
    repo=SettingsRepository(root/'access-policy')
    previous=repo.load()
    # Never accept an arbitrary policy root. This command is only for build_mcp_demo output.
    assert (root/'private-engine'/'genesis.db').is_file()
    assert not previous.mcp_enabled and not previous.mcp_projects
    files={str(p.relative_to(root/'snapshot')):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in (root/'snapshot').iterdir() if p.is_file()}
    async def exercise():
        params=StdioServerParameters(command=sys.executable,cwd=str(ROOT),args=[
            '-m','virtual_lab.integrations.mcp.server','--snapshot',str(root/'snapshot'),
            '--snapshot-sha256',metadata['snapshot_sha256'],'--settings-root',str(repo.root)])
        async with stdio_client(params) as (receive,send):
            async with ClientSession(receive,send) as session:
                initialized=await session.initialize()
                tools=(await session.list_tools()).tools
                transcript=[]
                async def call(name,args):
                    value=await session.call_tool(name,args)
                    if value.isError: raise RuntimeError('MCP call failed: '+name)
                    transcript.append({'tool':name,'result':value.structuredContent})
                    return value.structuredContent['data']
                assert (await call('list_projects',{}))['projects']==[]
                settings=previous.model_dump()
                settings.update(mcp_enabled=True,allow_cloud=True,
                    mcp_projects={metadata['project_id']:{'metadata':True,'reports':True,'spectrum':False}})
                repo.save(settings)
                projects=(await call('list_projects',{}))['projects']
                project=projects[0]['id']; experiment=projects[0]['experiments'][0]['id']
                exp=await call('get_experiment',{'project_id':project,'experiment_id':experiment})
                query={'project_id':project,'experiment_id':experiment,'dataset_id':exp['dataset_ids'][0]}
                integrity=await call('verify_dataset',query)
                assert integrity['integrity']=='PASS' and integrity['epistemic_state']=='UNKNOWN'
                denied=await session.call_tool('get_spectrum',query)
                assert denied.isError
                settings['mcp_projects'][project]['spectrum']=True; repo.save(settings)
                points=[]
                while True:
                    page=await call('get_spectrum',dict(query,offset=len(points),limit=200))
                    points.extend(page['points'])
                    if len(points)>=page['total_peaks']: break
                assert len(points)==metadata['peak_count']==467
                report=await call('get_report',query)
                body=dict(report); report_sha=body.pop('report_sha256')
                assert hashlib.sha256(json_bytes(body)).hexdigest()==report_sha
                assert report['summary']['peak_count']==len(points)
                assert report['epistemic_state']=='UNKNOWN'
                intent=await call('get_intent_status',{'project_id':project,'experiment_id':experiment})
                assert not intent['available']
                repo.save(previous)
                assert (await call('list_projects',{}))['projects']==[]
                assert (await session.call_tool('get_report',query)).isError
                return {'status':'passed','server':initialized.serverInfo.model_dump(),
                    'tools':[t.name for t in tools], 'peaks':len(points),'report_sha256':report_sha,
                    'snapshot_files_unchanged':True,'policy_restored':True,'chatgpt_connected':False,
                    'transport':'Real MCP SDK client/server over local stdio',
                    'scope':'Public BSA reference; software byte checks only; evidence UNKNOWN',
                    'transcript':transcript}
    try:
        result=asyncio.run(exercise())
        assert files=={str(p.relative_to(root/'snapshot')):hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (root/'snapshot').iterdir() if p.is_file()}
        (root/'mcp-verification.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k!='transcript'},indent=2))
    finally:
        repo.save(previous)


if __name__=='__main__': main()
