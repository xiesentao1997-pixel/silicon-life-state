"""Check durable dashboard authentication at the HTTP boundary on a disposable service."""
import hashlib
import http.client
import json
import tempfile
import unittest
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit

from acceptance_support import Local


class DashboardSession(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.service = Local(Path(tmp.name)).start()
        self.addCleanup(self.service.stop)
        self.port = urlsplit(self.service.base).port

    def request(self, path, data=None, **headers):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=8)
        try:
            conn.request('GET' if data is None else 'POST', '/api/' + path,
                         None if data is None else json.dumps(data),
                         {'Content-Type':'application/json', **headers})
            response = conn.getresponse()
            return response.status, json.loads(response.read()), response.getheader('Set-Cookie')
        finally:
            conn.close()

    def shares(self, response):
        code, body, cookie_header = response
        self.assertEqual(code, 200)
        self.assertNotIn('token', body)
        cookies = SimpleCookie(cookie_header)
        key = 'sls_dashboard_' + str(self.port)
        cookie = cookies[key]
        self.assertTrue(cookie['httponly'] and cookie['secure'])
        self.assertEqual(cookie['samesite'], 'Strict')
        self.assertGreater(int(cookie['max-age']), 0)
        self.assertEqual(cookie['path'], '/api/')
        return {'X-SLS-Dashboard':body['binding'], 'Cookie':f'{key}={cookie.value}'}

    def test_profile_reopen_restart_renew_rotate_and_revoke(self):
        service = self.service
        sid = service.subject('持久授权')
        code = service.api('pair/code', {'target':'dashboard'})['code']
        self.assertEqual(self.request('browser/pair', {'code':code}, Origin='https://example.org')[0], 403)
        origin = service.base
        shares = self.shares(self.request('browser/pair', {'code':code}, Origin=origin))
        for part in ('Cookie','X-SLS-Dashboard'):
            self.assertEqual(self.request('subjects', **{part:shares[part]})[0], 401)
        self.assertEqual(self.request('pair/rotate', {}, **shares)[0], 403)
        self.assertEqual(self.request('pair/rotate', {}, Origin='http://127.0.0.1:1', **shares)[0], 403)
        service.stop()
        service.start(port=self.port)
        self.assertEqual(self.request('subjects', **shares)[1]['subjects'][0]['subject_id'], sid)
        self.assertEqual(self.shares(self.request('browser/session', **shares)), shares)
        newer = self.shares(self.request('pair/rotate', {}, Origin=origin, **shares))
        self.assertNotEqual(shares, newer)
        self.assertEqual(self.request('subjects', **shares)[0], 401)
        self.assertEqual(self.request('subjects', **newer)[0], 200)
        status, body, clearing = self.request('logout', {}, Origin=origin, **newer)
        self.assertEqual(status, 200)
        self.assertTrue(body['revoked'])
        self.assertIn('Max-Age=0', clearing)
        self.assertEqual(self.request('subjects', **newer)[0], 401)

    def test_extension_uninstall_capability_only_retires_its_pairing(self):
        extension = 'chrome-extension://' + 'b' * 32
        one = self.service.ready['extension_code']
        two = self.service.api('pair/code', {'target':'extension'})['code']
        token = self.request('pair', {'code':one}, Origin=extension)[1]['token']
        other = self.request('pair', {'code':two}, Origin=extension)[1]['token']
        ticket = hashlib.sha256(('sls-extension-uninstall-v1:' + token).encode()).hexdigest()
        self.assertEqual(self.request('subjects', Origin=extension, Authorization='Bearer ' + ticket)[0], 401)
        self.assertEqual(self.request('extension/uninstalled', {'ticket':ticket}, Origin=extension)[0], 403)
        for attempt in range(2):
            self.assertEqual(self.request('extension/uninstalled', {'ticket':ticket}, Origin=self.service.base)[0], 200)
        self.assertEqual(self.request('subjects', Origin=extension, Authorization='Bearer ' + token)[0], 401)
        self.assertEqual(self.request('subjects', Origin=extension, Authorization='Bearer ' + other)[0], 200)

    def test_upgrade_exchanges_legacy_bearer_only_once(self):
        token = self.service.owner
        shares = self.shares(self.request('browser/upgrade', {}, Origin=self.service.base,
                                           Authorization='Bearer ' + token))
        self.assertEqual(self.request('subjects', **shares)[0], 200)
        self.assertEqual(self.service.raw('/api/subjects', token=token)[0], 401)
