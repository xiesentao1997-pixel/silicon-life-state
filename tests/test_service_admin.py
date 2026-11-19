"""Owner lifecycle entry points through a real service and independent OS-account CLI."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from acceptance_support import Local, ROOT, SERVER, ToolFailure

sys.path.insert(0, str(ROOT / 'apps/local-service'))
from server import InvocationBudget


class OwnerLifecycle(unittest.TestCase):
    def test_scoped_grant_inventory_revocation_after_restart_and_unpair(self):
        with tempfile.TemporaryDirectory() as directory:
            local = Local(Path(directory))
            local.start()
            try:
                sid = local.subject('Grant lifecycle')
                instance = local.api('instances', {'subject_id': sid, 'name': 'Window'})
                grant = local.api('credentials', {'subject_id': sid, 'instance_id': instance['instance_id']})
                model_token = grant['token']
                template = grant['stdio']
                self.assertEqual(set(template), {'command', 'args'})
                self.assertEqual(template['command'], sys.executable)
                self.assertTrue(Path(template['args'][0]).is_absolute())
                self.assertNotIn(model_token, json.dumps(template))
                request = {"jsonrpc":"2.0","id":1,"method":"initialize","params":{
                    "protocolVersion":"2025-11-25","clientInfo":{"name":"owner-test","version":"1"},"capabilities":{}}}
                wire = subprocess.run([template['command'], *template['args']], input=json.dumps(request)+'\n',
                        cwd=directory, env={**os.environ, "SILICON_AGENT_TOKEN":model_token,"SILICON_MCP_URL":local.base+"/mcp"},
                        capture_output=True, text=True, timeout=10, check=True)
                self.assertEqual('silicon-life-state', json.loads(wire.stdout)['result']['serverInfo']['name'])
                self.assertNotIn('stdio', local.api('export'))
                self.assertNotIn(template['args'][0], json.dumps(local.raw('/api/health')[1]))
                self.assertNotIn(template['args'][0], json.dumps(local.api('export')))
                local.stop()
                local.start()
                rows = local.api('credentials')['grants']
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['instance_id'], instance['instance_id'])
                self.assertEqual(rows[0]['subject_id'], sid)
                self.assertEqual(set(rows[0]), {'grant_id', 'subject_id', 'instance_id', 'created_at'})
                self.assertNotIn('grants', local.api('export'))
                local.api('credentials/revoke', {'grant_id': rows[0]['grant_id']})
                with self.assertRaises(ToolFailure):
                    local.tool(model_token, 'get_own_state')
                self.assertEqual([], local.api('credentials')['grants'])
                result = subprocess.run([sys.executable, str(SERVER), '--data-dir',directory,'--unpair-all'],
                                        capture_output=True, check=True)
                self.assertGreater(json.loads(result.stdout)['revoked_clients'], 0)
                self.assertEqual(local.raw('/api/subjects',token=local.owner)[0], 401)
            finally:
                local.stop()

    def test_mcp_invocation_limit_is_local_to_grant_and_expires(self):
        budget = InvocationBudget(maximum=2, seconds=60)
        with patch('server.time.monotonic', side_effect=[100,100,110,110,150,161]):
            self.assertEqual(0, budget.admit('first'))
            self.assertEqual(0, budget.admit('first'))
            self.assertEqual(50, budget.admit('first'))
            self.assertEqual(0, budget.admit('second'))
            self.assertEqual(10, budget.admit('first'))
            self.assertEqual(0, budget.admit('first'))
