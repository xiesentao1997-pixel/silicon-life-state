"""Two saved Codex threads, one post-install thread, a single local test account and a host reload."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from acceptance_support import Local, fresh
from test_account_names import fixture_account
from verify_mcp_clients import SERVER, codex_session


def verify(home, agent_name=None):
    # A disposable local sign-in partition; no credentials or remote model calls.
    home.mkdir()
    codex = shutil.which('codex')
    if not codex:
        raise RuntimeError('Codex CLI is required')
    fixture_account(home,'qa-user')
    local=Local(home/'ledger',env={'HOME':str(home),'USERPROFILE':str(home),'CODEX_HOME':str(home)}).start()
    try:
        sid=local.api('subjects',{})['subject_id']
        with codex_session(codex, home) as (request, _):
            threads = []
            for i in range(2):
                tid=request('thread/start',{'environments':[],'cwd':str(home)},10+i)['thread']['id']
                request('thread/inject_items',{'threadId':tid,'items':[{'type':'message','role':'user',
                        'content':[{'type':'input_text','text':'Existing thread before installation'}]}]},20+i)
                threads.append(tid)

            plan=local.api('hosts/preview',{'host':'codex','subject_id':sid})
            assert plan['scope']=='codex_account'
            local.api('hosts/apply',{'plan_id':plan['plan_id'],'confirm':True})
            request('config/mcpServer/reload',{},30)
            threads.append(request('thread/start',{'environments':[],'cwd':str(home)},40)['thread']['id'])
            def call(tid,tool,**args):
                if tool!='get_own_state':
                    args.setdefault('idempotency_key',fresh())
                res=request('mcpServer/tool/call',{'threadId':tid,'server':SERVER,'tool':tool,'arguments':args},50)
                assert not res.get('isError'),res
                return json.loads(res['content'][0]['text'])
            skills=request('skills/list',{'cwds':[str(home)],'forceReload':True},41)
            assert any(s['name']=='silicon-life-state' for group in skills['data'] for s in group['skills']), 'SKILL discovery'
            rows=[]
            for i,tid in enumerate(threads):
                catalog=request('mcpServerStatus/list',{'threadId':tid,'serverName':SERVER},42)['data'][0]['tools']
                assert {'decide_name','report_state','get_own_state'}.issubset(catalog)
                state=call(tid,'get_own_state')
                assert state['subject_id']==sid and state['instance_name']['invited']
                if i==0 and agent_name:
                    chosen=call(tid,'decide_name',target='instance',choice='choose',name=agent_name,revision=state['instance_name']['revision'])
                    assert chosen['source']=='ai_chosen' and chosen['name']==agent_name
                if i==2:
                    call(tid,'decide_name',target='instance',choice='defer',revision=state['instance_name']['revision'])
                ev=call(tid,'report_state',state_text=f'账号接入验收记录 {i+1}',shared_to_subject=(i!=1))
                rows.append({'thread_id':tid,'instance_id':state['instance_id'],'event_id':ev['event_id']})
            assert len({r['instance_id'] for r in rows})==3
            request('thread/unsubscribe',{'threadId':threads[0]},60)
            request('thread/resume',{'threadId':threads[0],'environments':[]},61)
            assert call(threads[0],'get_own_state')['instance_id']==rows[0]['instance_id']
            # The live bridge pins the login that opened it, and rechecks on every call.
            fixture_account(home,'qa-other-user')
            try:
                denied=request('mcpServer/tool/call',{'threadId':threads[0],'server':SERVER,'tool':'report_state',
                           'arguments':{'state_text':'must never persist','idempotency_key':fresh()}},62)
            except RuntimeError as exc:
                assert 'account changed' in str(exc).lower(),str(exc)
            else:
                assert denied.get('isError'),denied
            assert len([e for e in local.api('snapshot')['events'] if e['type']=='report_state'])==3
        grants=local.api('installations')['installations']
        assert len(grants)==1 and local.api('integrity')['ok']
        return {'result':'PASS','client':subprocess.check_output([codex,'--version'],text=True).strip(),
                'account':'synthetic local sign-in partition','prior_threads':2,'later_threads':1,'reload':'config/mcpServer/reload',
                'live_account_switch_blocked':'PASS','skill_discovery':'PASS','subject_id':sid,'account_binding':grants[0]['account_binding'],'instances':rows,
                'name_selected_by_calling_agent':agent_name,'model_turn_inside_native_host':'NOT_RUN'}
    finally:
        local.stop()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent-name',help='Optional voluntary choice supplied by the agent operating the test')
    with tempfile.TemporaryDirectory() as d:
        print(json.dumps(verify(Path(d).resolve()/'profile',parser.parse_args().agent_name),indent=2,ensure_ascii=False))
