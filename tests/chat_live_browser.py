"""Opt-in real browser + local model inference, using only disposable state.

Needs Playwright, a Chromium executable and a CPU-compatible llama-server with a
tool-capable model. No model, shell test fixture or public inference API is supplied
by the product. The model may decline to use tools. This is recorded separately.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

from acceptance_support import Local
from live_model_chat import check_database


WARM_UP = 'What is 2 + 2? Please keep the answer brief.'
PROMPT = ('Please call the report_state function once now to leave a brief handoff about the math question '
          'you just answered. Set only state_text, choosing the words yourself. You may decline if you prefer. '
          'After the call, tell me whether you recorded it.')
INFERENCE_OPTIONS = ['--jinja','--reasoning','off','--temp','0.2','--seed','42','-n','512',
                     '-t','4','-c','4096','-np','1']


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024*1024),b''):
            digest.update(data)
    return digest.hexdigest()


@contextmanager
def inference(binary, weights, model, tmp):
    with socket.socket(socket.AF_INET) as sock:
        sock.bind(('127.0.0.1',0))
        port = sock.getsockname()[1]
    env={**os.environ}
    lib_dir = str(binary.parent)
    env['LD_LIBRARY_PATH'] = os.pathsep.join(filter(None,(lib_dir,env.get('LD_LIBRARY_PATH',''))))
    command = [str(binary),'-m',str(weights),'--host','127.0.0.1','--port',str(port),
               '-a',model,*INFERENCE_OPTIONS]
    with (tmp/'model-runtime.log').open('w',encoding='utf-8') as log:
        process = subprocess.Popen(command,env=env,stdout=log,stderr=log)
        try:
            deadline = time.monotonic()+90
            while time.monotonic()<deadline:
                if process.poll() is not None:
                    raise RuntimeError(f'llama-server exited before readiness (code {process.returncode})')
                connection=http.client.HTTPConnection('127.0.0.1',port,timeout=1)
                try:
                    connection.request('GET','/health')
                    response=connection.getresponse()
                    if response.status==200 and json.loads(response.read()).get('status')=='ok':
                        break
                except (OSError,json.JSONDecodeError):
                    pass
                finally:
                    connection.close()
                time.sleep(.25)
            else:
                raise RuntimeError('llama-server readiness timed out')
            yield f'http://127.0.0.1:{port}/v1'
        finally:
            process.terminate()
            try: process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    from playwright.sync_api import expect, sync_playwright
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--llama-server',required=True,type=Path)
    p.add_argument('--weights',required=True,type=Path)
    p.add_argument('--model',required=True)
    p.add_argument('--warm-up',default=WARM_UP,help='Optional preceding conversation turn; empty to skip')
    p.add_argument('--prompt',default=PROMPT,help='The exact user message for this dedicated model session')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    binary=args.llama_server.resolve(strict=True)
    weights=args.weights.resolve(strict=True)
    evidence={'checked_at':datetime.now(timezone.utc).isoformat(),'provider':'local llama.cpp model inference',
              'model':args.model,'weights_sha256':sha256(weights),'inference_binary_sha256':sha256(binary),
              'prompt':args.prompt,'requested_tool_choice':'auto','inference_options':INFERENCE_OPTIONS}
    with tempfile.TemporaryDirectory(prefix='sls-genuine-model-') as directory, sync_playwright() as pw:
        tmp=Path(directory)
        with inference(binary,weights,args.model,tmp) as endpoint:
            service=Local(tmp/'data').start()
            try:
                subject=service.subject('硅基生命状态 · 本地模型联调')
                window=service.api('instances',{'subject_id':subject,'name':'本机模型对话分身'})
                options={'executable_path':os.environ['SILICON_CHROMIUM']} if os.getenv('SILICON_CHROMIUM') else {}
                browser=pw.chromium.launch(**options)
                try:
                    evidence['chromium']=browser.version
                    page=browser.new_page(viewport={'width':1400,'height':1080},locale='zh-CN')
                    errors=[]
                    page.on('pageerror',lambda exc: errors.append(str(exc)))
                    code=service.api('pair/code',{'target':'dashboard'})['code']
                    page.goto(service.base+'/#pair='+code+'&view=chat&subject='+subject)
                    page.locator('#chat-url').fill(endpoint)
                    page.locator('#chat-model').fill(args.model)
                    page.locator('#chat-connect').click()
                    expect(page.locator('#chat-text')).to_be_enabled(timeout=20000)
                    turns=[]
                    for prompt in filter(None,(args.warm_up,args.prompt)):
                        page.locator('#chat-text').fill(prompt)
                        with page.expect_response(lambda r:r.url.endswith('/api/chat/message'),timeout=240000) as res:
                            page.locator('#chat-send').click()
                        response=res.value.json()
                        if res.value.status!=200:
                            raise RuntimeError('chat/message returned '+json.dumps(response.get('error',{}),ensure_ascii=False))
                        if response['reply']:
                            expect(page.locator('#chat-transcript')).to_contain_text(response['reply'])
                        turns.append({'prompt':prompt,'reply':response['reply'],'tool_events':response['tool_events'],
                                      'tool_errors':response.get('tool_errors',[]),'status':response.get('status')})
                    evidence['turns']=turns
                    event_ids=[r['event_id'] for turn in turns for r in turn['tool_events']]
                    evidence['event_ids']=event_ids
                    evidence['instance_id']=window['instance_id']
                    expect(page.locator('.chat-receipt')).to_have_count(len(event_ids))
                    page.screenshot(path=str(args.output/'genuine-model-chat.jpg'),type='jpeg',quality=90)
                    snapshot=service.api('snapshot?subject_id='+subject)
                    events=[r for r in snapshot['events'] if r['event_id'] in event_ids]
                    assert len(events)==len(set(event_ids))
                    for row in events:
                        assert row['instance_id']==window['instance_id'] and row['source']=='agent_direct'
                    if event_ids:
                        assert check_database(tmp/'data'/'state.sqlite3',event_ids)
                    evidence['matched_sqlite_ids']=sorted(set(event_ids))
                    evidence['events']=[{key:row.get(key) for key in
                                         ('event_id','instance_id','type','source','created_at','payload',
                                          'model_version','adapter_version','hash')} for row in events]
                    evidence['integrity']=service.api('integrity')
                    assert evidence['integrity']['ok']
                    evidence['result']='REAL_MODEL_REPLIED_NO_STATE_REPORT'
                    reports=[row for row in events if row['type']=='report_state']
                    if reports:
                        observed=snapshot['instances'][0]['state']
                        assert observed['event_id'] in {row['event_id'] for row in reports}
                        page.locator('.nav-item[data-val=overview]').click()
                        statement=observed['payload'].get('state_text')
                        if statement:
                            expect(page.locator('.big-quote').first).to_have_text(statement)
                        page.screenshot(path=str(args.output/'genuine-model-dashboard.jpg'),type='jpeg',quality=90)
                        page.locator('[data-act=event]').first.click()
                        expect(page.locator('dialog')).to_contain_text(observed['event_id'])
                        expect(page.locator('dialog')).to_contain_text(observed['hash'])
                        evidence['result']='PASS'
                    evidence['page_errors']=errors
                    assert not errors, errors
                finally:
                    browser.close()
            finally:
                service.stop()
    raw=json.dumps(evidence,ensure_ascii=False,indent=2)+'\n'
    (args.output/'genuine-model-browser.json').write_text(raw,encoding='utf-8')
    print(raw)


if __name__=='__main__':
    main()
