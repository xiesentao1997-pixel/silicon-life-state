"""MV3 packaging and shipped extension REST client integration. No native browser emulation."""
import json
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / 'apps' / 'extension'


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.files = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if 'src' in attrs:
            self.files.append(attrs['src'])
        if tag == 'link' and 'href' in attrs:
            self.files.append(attrs['href'])


class ExtensionTest(unittest.TestCase):
    def test_package_permissions_resources_and_controls(self):
        manifest = json.loads((EXT/'manifest.json').read_text())
        self.assertEqual(3, manifest['manifest_version'])
        self.assertEqual(['http://127.0.0.1/*'], manifest['host_permissions'])
        self.assertEqual({'https://chatgpt.com/*','https://claude.ai/*','https://gemini.google.com/*'},
                         set(manifest['optional_host_permissions']))
        for disallowed in ['content_scripts','externally_connectable','web_accessible_resources']:
            self.assertNotIn(disallowed, manifest)
        for permission in ['cookies','webRequest','tabs','debugger','history']:
            self.assertNotIn(permission, manifest['permissions'])
        parser = Markup()
        parser.feed((EXT/manifest['side_panel']['default_path']).read_text())
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        for path in parser.files + list(manifest['icons'].values()) + [manifest['background']['service_worker']]:
            self.assertTrue((EXT/path).is_file(), path)
        for platform in ('chatgpt','claude','gemini'):
            self.assertTrue((EXT/'adapters'/(platform+'.js')).is_file())
        bound_ids = re.findall(r"(?:\$|click)\('([a-z-]+)'", (EXT/'panel.js').read_text())
        self.assertFalse(set(bound_ids) - set(parser.ids))

    @unittest.skipUnless(shutil.which('node'), 'Node required only for JS integration testing')
    def test_binding_collision(self):
        result = subprocess.run(['node', str(ROOT/'tests/extension_binding.mjs')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node required only for JS integration testing')
    def test_client_on_real_http_loopback(self):
        # Use the actual api.js module, real HTTP and real SQLite. Only extension storage
        # and runtime ID are supplied here. Native Chrome coverage is a separate script.
        with tempfile.TemporaryDirectory() as directory:
            with subprocess.Popen([sys.executable, str(ROOT/'apps/local-service/server.py'),
                                   '--port','0','--no-browser','--json-ready','--data-dir',directory],
                                  stdout=subprocess.PIPE, text=True) as process:
                try:
                    ready = json.loads(process.stdout.readline())
                    src = r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const ready = JSON.parse(readFileSync(0,'utf8'));
const code = readFileSync(process.argv[1]);
const {localApi,key,endpoint,textOf} = await import('data:text/javascript;base64,'+code.toString('base64'));
const state = {port:Number(new URL(ready.base_url).port)};
globalThis.chrome = {runtime:{id:'a'.repeat(32)},storage:{local:{get:async()=>({...state})}}};
assert.throws(()=>endpoint('invalid'));
const pairing=await localApi('pair',{anonymous:true,body:{code:ready.extension_code}});
state.token=pairing.token;
const subject=await localApi('subjects',{body:{name:'验收主体',idempotency_key:key()}});
const instance=await localApi('instances',{body:{name:'验收分身',subject_id:subject.subject_id,idempotency_key:key()}});
const args={source:'agent_visible_text',instance_id:instance.instance_id,text:'选区存档',adapter:'chatgpt',adapter_version:'1.0.0',idempotency_key:key()};
const item=await localApi('observations',{body:args});
assert.equal(item.source,'agent_visible_text');assert.equal(item.adapter_version,'1.0.0');assert.equal(textOf(item),'选区存档');
assert.equal((await localApi('observations',{body:args})).event_id,item.event_id);
await assert.rejects(localApi('observations',{body:{...args,source:'agent_direct',idempotency_key:key()}}));
await localApi('settings',{body:{observation_enabled:false,idempotency_key:key()}});
await assert.rejects(localApi('observations',{body:{...args,idempotency_key:key()}}));
const snap=await localApi('snapshot');assert(snap.events.some(e=>e.event_id===item.event_id));
assert.equal(snap.instances[0].state,null);
chrome.runtime.id='b'.repeat(32);
await assert.rejects(localApi('snapshot'), {status:403});
chrome.runtime.id='a'.repeat(32);
await localApi('logout',{body:{}});
await assert.rejects(localApi('snapshot'), {status:401});
"""
                    result = subprocess.run(['node','--input-type=module','-e',src,str(EXT/'api.js')],
                                            input=json.dumps(ready),text=True,capture_output=True,timeout=30)
                    self.assertEqual(result.returncode,0, result.stderr)
                finally:
                    process.terminate()


if __name__ == '__main__':
    unittest.main()
