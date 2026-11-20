"""Black-box test client. Every test owns a temporary DB and a real subprocess."""
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / 'apps/local-service/server.py'
PROTOCOL = '2026-07-28'
READ_TOOLS = {'read_event_history', 'read_subject_memory', 'get_request_status', 'get_own_state'}


def fresh():
    return str(uuid.uuid4())


class ToolFailure(Exception):
    pass


class Local:
    def __init__(self, directory, env=None, server=SERVER):
        self.directory = Path(directory).resolve()
        self.server = Path(server).resolve()
        self.process = None
        self.env = {**os.environ, **(env or {}), 'PYTHONIOENCODING': 'utf-8'}

    def start(self, *, bootstrap=None, python_options=(), port=0):
        launcher = [str(bootstrap)] if bootstrap else []
        self.process = subprocess.Popen(
            [sys.executable, *python_options, *launcher, str(self.server), '--data-dir', str(self.directory), '--port', str(port),
             '--json-ready', '--no-browser'], cwd=ROOT, env=self.env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8')
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError(self.process.stderr.read())
        self.ready = json.loads(line)
        self.base = self.ready['base_url']
        status, body = self.raw('/api/pair', {'code': self.ready['code']})
        assert status == 200, (status, body)
        self.owner = body['token']
        return self

    def stop(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.communicate()
            self.process = None

    def raw(self, path, data=None, token=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', urlsplit(self.base).port, timeout=20)
        h = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if token:
            h['Authorization'] = 'Bearer ' + token
        h.update(headers or {})
        try:
            conn.request('GET' if data is None else 'POST', path,
                         None if data is None else json.dumps(data).encode(), h)
            res = conn.getresponse()
            payload = res.read()
            return res.status, json.loads(payload) if payload else {}
        finally:
            conn.close()

    def observation(self, data):
        if not hasattr(self, 'ext_token'):
            ident = 'abcdefghijklmnopabcdefghijklmnop'
            self.ext_headers = {'Origin': 'chrome-extension://' + ident, 'X-SLS-Extension': ident}
            status, pair = self.raw('/api/pair', {'code': self.ready['extension_code']}, headers=self.ext_headers)
            assert status == 200, (status, pair)
            self.ext_token = pair['token']
        status, result = self.raw('/api/observations', {'idempotency_key': fresh(), **data},
                                  self.ext_token, self.ext_headers)
        assert status == 200, (status, result)
        return result

    def api(self, path, data=None):
        if data is not None:
            data = {'idempotency_key': fresh(), **data}
        status, result = self.raw('/api/' + path, data, self.owner)
        if status != 200:
            raise AssertionError((path, status, result))
        return result

    def tool(self, token, name, /, **arguments):
        if name not in READ_TOOLS:
            arguments.setdefault('idempotency_key', fresh())
        meta = {'io.modelcontextprotocol/protocolVersion': PROTOCOL,
                'io.modelcontextprotocol/clientCapabilities': {},
                'io.modelcontextprotocol/clientInfo': {'name': 'acceptance-client', 'version': '1.0'}}
        msg = {'jsonrpc': '2.0', 'id': fresh(), 'method': 'tools/call',
               'params': {'_meta': meta, 'name': name, 'arguments': arguments}}
        headers = {'MCP-Protocol-Version': PROTOCOL, 'Mcp-Method': 'tools/call', 'Mcp-Name': name,
                   'Accept': 'application/json, text/event-stream'}
        status, rpc = self.raw('/mcp', msg, token, headers)
        if status != 200 or 'error' in rpc:
            raise ToolFailure((status, rpc.get('error')))
        result = rpc['result']
        if result.get('isError'):
            raise ToolFailure(json.loads(result['content'][0]['text']))
        return result['structuredContent']

    def subject(self, name='验收主体'):
        return self.api('subjects', {'name': name})['subject_id']

    def window(self, subject, name):
        row = self.api('instances', {'subject_id': subject, 'name': name})
        grant = self.api('credentials', {'subject_id': subject, 'instance_id': row['instance_id']})
        return row, grant['token']
