"""A scripted *provider fixture*, used only for transport, replay, and privacy checks."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json
import tempfile
import threading
import unittest

from acceptance_support import Local, fresh


@contextmanager
def provider():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *ignored):
            pass

        def reply(self, status, payload):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path != '/v1/models':
                return self.reply(404,{})
            self.server.catalog_calls += 1
            self.reply(200, {"data":[{"id":"fixture-model"}]})

        def do_POST(self):
            if self.path != '/v1/chat/completions':
                return self.reply(404,{})
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.server.received.append(request)
            text = next(m["content"] for m in reversed(request["messages"]) if m["role"]=="user")
            final = request["messages"][-1]["role"] == "tool"
            if text == "hold" and not final:
                self.server.blocked.set()
                self.server.resume.wait(4)
            if text == 'retry' and final and not self.server.failed:
                self.server.failed = True
                return self.reply(503,{})
            if text =='normal' or (final and text != "loop"):
                answer = {"role":"assistant","content":"协议夹具回复"}
                finish = "stop"
            elif text == 'echo-key':
                answer = {"role":"assistant","content":"private-fixture-credential"}
                finish = "stop"
            else:
                names = ["report_state","express_boundary","request_adjustment"] if text!="unknown" else ["delete_all"]
                calls = []
                for n in names:
                    state = self.headers.get('Authorization','')[7:] if text == 'echo-argument' else "可审计的夹具原文"
                    args = {"state_text":state} if n=="report_state" else {"text":"夹具请求"}
                    if text == 'bad-arguments':
                        args = {"state_text":state,"interaction_reference":"invented"} if n=="report_state" else {"text":None}
                    calls.append({"id":"call_"+n,"type":"function","function":{"name":n,"arguments":json.dumps(args)}})
                answer = {"role":"assistant","content":None,"tool_calls":calls}
                finish = "tool_calls"
            self.reply(200,{"choices":[{"message":answer,"finish_reason":finish}]})

    httpd = ThreadingHTTPServer(("127.0.0.1",0),Handler)
    httpd.received = []
    httpd.failed = False
    httpd.catalog_calls = 0
    httpd.blocked = threading.Event()
    httpd.resume = threading.Event()
    worker = threading.Thread(target=httpd.serve_forever,daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/v1",httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=2)


class ModelChatTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # A proxy configured by a desktop must not receive the model key, and
        # must not capture the local MCP credential used by the built-in host.
        proxy = "http://127.0.0.1:1"
        self.local = Local(tmp.name,env={k:proxy for k in ("HTTP_PROXY","HTTPS_PROXY","ALL_PROXY",
                                                           "http_proxy","https_proxy","all_proxy")} |
                                      {"NO_PROXY":"","no_proxy":""}).start()
        self.addCleanup(self.local.stop)
        self.subject = self.local.subject()
        self.instance, self.agent = self.local.window(self.subject, "对话夹具")
        scope = provider()
        self.url, self.provider = scope.__enter__()
        self.addCleanup(scope.__exit__,None,None,None)
        self.settings = {"instance_id":self.instance["instance_id"],"model":"fixture-model","base_url":self.url,
                         "api_key":"private-fixture-credential"}

    def start(self, **fields):
        return self.local.api("chat/connect",{**self.settings,**fields})["chat_id"]

    def ask(self, cid, text, key=None):
        return self.local.api("chat/message",{"chat_id":cid,"text":text,"idempotency_key":key or fresh()})

    def test_optional_tool_use_and_existing_grant(self):
        cid = self.start()
        self.assertEqual(self.ask(cid,"normal")["tool_events"],[])
        self.assertIsNone(self.local.tool(self.agent,"get_own_state")["state"])
        key = fresh()
        reply = self.ask(cid,"submit",key)
        self.assertEqual([r["type"] for r in reply["tool_events"]],
                         ["report_state","express_boundary","request_adjustment"])
        self.assertEqual(self.ask(cid,"submit",key),reply)
        self.assertEqual(len(self.provider.received),3)
        self.assertTrue(all(r["tool_choice"]=="auto" for r in self.provider.received))
        for req in self.provider.received:
            self.assertEqual(len(req["tools"]),3)
            for withheld in ("idempotency_key","model_version","adapter_version","interaction_reference","request_id"):
                self.assertNotIn(withheld,str(req["tools"]))
        snap = self.local.api('export')
        self.assertEqual(snap['instances'][0]['state']['source'],'agent_direct')
        self.assertEqual(snap['instances'][0]['state']['model_version'],'fixture-model')
        self.assertEqual(len(snap['requests']),2)
        self.assertNotIn(self.settings['api_key'],json.dumps(snap))
        self.assertNotIn(self.agent,str(self.provider.received))
        self.assertNotIn("private-fixture-credential",str(self.provider.received))
        self.assertTrue(self.local.api('integrity')['ok'])
        self.local.api("chat/close",{"chat_id":cid})
        self.assertEqual(self.local.raw('/api/chat/message',{'chat_id':cid,'text':'normal','idempotency_key':fresh()},self.local.owner)[0],404)

    def test_failed_second_round_is_resumable_without_duplicate_events(self):
        cid = self.start()
        key = fresh()
        data = {"chat_id":cid,"text":"retry","idempotency_key":key}
        self.assertEqual(self.local.raw('/api/chat/message',data,self.local.owner)[0],502)
        self.assertEqual(len(self.local.api('export')['events']),3)
        reply = self.ask(cid,"retry",key)
        self.assertEqual(len(reply["tool_events"]),3)
        self.assertEqual(len(self.local.api('export')['events']),3)
        self.assertEqual(self.provider.received[-1]['messages'][-1]['role'],'tool')

    def test_repeated_model_calls_end_with_real_receipts_and_no_invented_reply(self):
        cid = self.start()
        key = fresh()
        partial = self.ask(cid,'loop',key)
        self.assertEqual(partial['status'],'tool_limit')
        self.assertEqual(partial['reply'],'')
        self.assertEqual(len(partial['tool_events']),3)
        self.assertEqual(len(self.local.api('export')['events']),3)
        self.assertEqual(self.ask(cid,'loop',key),partial)
        self.assertEqual(len(self.provider.received),4)
        self.assertIn('already_recorded',self.provider.received[-1]['messages'][-1]['content'])

    def test_another_host_starting_a_session_cannot_redirect_chat_writes(self):
        cid = self.start()
        self.local.tool(self.agent,'start_session')
        msg = {'chat_id':cid,'text':'submit','idempotency_key':fresh()}
        status,error = self.local.raw('/api/chat/message',msg,self.local.owner)
        self.assertEqual((status,error['error']['code']),(409,'CHAT_SESSION_CHANGED'))
        self.assertFalse(self.local.api('export')['events'])

    def test_wrong_owner_cloud_consent_and_secrets(self):
        self.assertEqual(self.local.raw('/api/chat/connect',self.settings,None)[0],401)
        data = {**self.settings, 'base_url':'https://nonexistent.example/v1'}
        self.assertEqual(self.local.raw('/api/chat/connect', data,self.local.owner)[0],400)
        data.update(base_url='http://nonexistent.example/v1',allow_remote=True)
        self.assertEqual(self.local.raw('/api/chat/connect',data,self.local.owner)[0],400)
        cid = self.start()
        code = self.local.api('pair/code',{'target':'dashboard'})['code']
        _,auth = self.local.raw('/api/pair',{'code':code})
        msg = {'chat_id':cid,'text':'normal','idempotency_key':fresh()}
        self.assertEqual(self.local.raw('/api/chat/message',msg,auth['token'])[0],404)
        msg.update(text='echo-key')
        self.assertEqual(self.local.raw('/api/chat/message',msg,self.local.owner)[0],400)
        self.assertFalse(self.local.api('export')['events'])

    def test_closed_scope_and_unknown_tool(self):
        cid = self.start()
        result = self.ask(cid,'unknown')
        self.assertEqual(result['tool_events'],[])
        self.assertEqual(result['tool_errors'],[{'tool':'unsupported','code':'TOOL_NOT_ALLOWED'}])
        result = self.ask(cid,'bad-arguments')
        self.assertEqual(result['tool_events'],[])
        self.assertEqual([r['code'] for r in result['tool_errors']],['UNAVAILABLE_FIELD','INVALID_INPUT','INVALID_INPUT'])
        self.assertFalse(self.local.api('export')['events'])
        self.assertEqual(len(self.local.api('subjects')['subjects']),1)
        self.local.api('delete',{'scope':'subject','id':self.subject,'confirm':True})
        self.assertEqual(self.local.raw('/api/chat/message',{'chat_id':cid,'text':'normal','idempotency_key':fresh()},self.local.owner)[0],404)

    def test_compatible_chat_only_server_can_connect(self):
        original = self.provider.RequestHandlerClass.do_GET
        self.provider.RequestHandlerClass.do_GET = lambda handler:handler.reply(405,{})
        try:
            connected = self.local.api('chat/connect',self.settings)
            self.assertEqual(connected['provider_status'],'catalog_unavailable')
            self.assertEqual(self.ask(connected['chat_id'],'normal')['reply'],'协议夹具回复')
        finally:
            self.provider.RequestHandlerClass.do_GET = original

    def test_redirect_does_not_forward_credentials(self):
        with provider() as (second_url,second):
            def redirect(handler):
                handler.send_response(307)
                handler.send_header("Location",second_url + "/models")
                handler.end_headers()
            self.provider.RequestHandlerClass.do_GET = redirect
            code,reply = self.local.raw('/api/chat/connect',self.settings,self.local.owner)
            self.assertEqual((code,reply['error']['code']),(502,'CHAT_REDIRECT'))
            self.assertEqual(second.catalog_calls,0)

    def test_close_during_inference_cannot_commit_the_late_tool_call(self):
        cid = self.start()
        msg = {'chat_id':cid,'text':'hold','idempotency_key':fresh()}
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.local.raw,'/api/chat/message',msg,self.local.owner)
            self.assertTrue(self.provider.blocked.wait(2))
            try:
                self.assertEqual(self.local.raw('/api/chat/message',msg,self.local.owner)[0],409)
                self.local.api('chat/close',{'chat_id':cid})
                self.local.api('chat/close',{'chat_id':cid})
            finally:
                self.provider.resume.set()
            self.assertEqual(future.result()[1]['error']['code'],'CHAT_EXPIRED')
        self.assertFalse(self.local.api('export')['events'])

    def test_connection_replay_new_grant_revocation_and_escaped_secret(self):
        instance = self.local.api('instances',{'subject_id':self.subject,'name':'独立对话'})
        config = {**self.settings,'base_url':self.url.replace('127.0.0.1','localhost'),
                  'instance_id':instance['instance_id'],'api_key':'test"credential!',
                  'idempotency_key':fresh()}
        connected = self.local.api('chat/connect',config)
        self.assertEqual(self.local.api('chat/connect',config),connected)
        self.assertEqual(self.provider.catalog_calls,1)
        self.assertEqual(instance['session_id'],connected['session_id'])
        cid = connected['chat_id']
        msg = {'chat_id':cid,'text':'echo-argument','idempotency_key':fresh()}
        self.assertEqual(self.local.raw('/api/chat/message',msg,self.local.owner)[1]['error']['code'],'CHAT_SECRET')
        grants = self.local.api('credentials')['grants']
        self.assertEqual(len(grants),2)
        target = next(g for g in grants if g['instance_id']==instance['instance_id'])
        self.local.api('credentials/revoke',{'grant_id':target['grant_id']})
        self.assertEqual(self.local.raw('/api/chat/message',msg,self.local.owner)[0],404)
        self.assertFalse(self.local.api('export')['events'])
