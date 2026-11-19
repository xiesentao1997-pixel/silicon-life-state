"""Independent browser pairing and grant isolation. Uses only disposable directories."""
import concurrent.futures
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/local-service'))
from access import Access, AccessError


class BrowserPairing(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.access = Access(temp.name)
        self.web = 'http://127.0.0.1:47831'
        self.extension = 'chrome-extension://' + 'a' * 32

    def test_one_time_and_target_bound(self):
        code = self.access.issue_code('extension')['code']
        with self.assertRaises(AccessError):
            self.access.exchange(code, self.web)
        token = self.access.exchange(code, self.extension)['token']
        self.access.check(token, self.extension)
        with self.assertRaises(AccessError):
            self.access.exchange(code, self.extension)
        with self.assertRaises(AccessError):
            self.access.check(token, self.web)

    def test_concurrent_exchange_only_one(self):
        code = self.access.issue_code('dashboard')['code']
        def exchange(_):
            try:
                return self.access.exchange(code, self.web)['token']
            except AccessError:
                return None
        with concurrent.futures.ThreadPoolExecutor(4) as workers:
            self.assertEqual(1, sum(token is not None for token in workers.map(exchange, range(8))))

    def test_raw_secrets_absent_from_access_db(self):
        code = self.access.issue_code('dashboard')['code']
        before = self.access.path.read_bytes()
        token = self.access.exchange(code, self.web)['token']
        self.assertNotIn(code.encode(), before)
        self.assertNotIn(code.encode(), self.access.path.read_bytes())
        self.assertNotIn(token.encode(), self.access.path.read_bytes())

    def test_expiry_and_revocation(self):
        code = self.access.issue_code('dashboard')['code']
        with sqlite3.connect(self.access.path) as db:
            db.execute('UPDATE codes SET expires=0')
        with self.assertRaises(AccessError):
            self.access.exchange(code, self.web)
        token = self.access.exchange(self.access.issue_code('dashboard')['code'], self.web)['token']
        self.access.revoke(token)
        with self.assertRaises(AccessError):
            self.access.check(token,self.web)

    def test_preference_persistence_and_erase(self):
        def pair(target, origin):
            return self.access.exchange(self.access.issue_code(target)['code'], origin)['token']
        a = pair('dashboard', self.web)
        b = pair('extension', self.extension)
        self.assertFalse(self.access.settings(False)['observation_enabled'])
        self.assertFalse(Access(self.access.path.parent).settings()['observation_enabled'])
        self.access.reset(a)
        self.access.check(a, self.web)
        with self.assertRaises(AccessError):
            self.access.check(b, self.extension)
        self.assertTrue(self.access.settings()['observation_enabled'])

    def test_cli_reset_cancels_unclaimed_codes_and_active_pairings(self):
        code = self.access.issue_code('dashboard')['code']
        first = self.access.exchange(self.access.issue_code('extension')['code'], self.extension)
        closed = self.access.unpair_all()
        self.assertEqual(closed, {'revoked_clients': 1, 'cancelled_codes': 1})
        with self.assertRaises(AccessError):
            self.access.check(first['token'], self.extension)
        with self.assertRaises(AccessError):
            self.access.exchange(code, self.web)

    def test_preference_retry_preserves_a_newer_pause(self):
        token = self.access.exchange(self.access.issue_code('dashboard')['code'], self.web)['token']
        self.access.settings(True, token=token, key='enable-key')
        self.access.settings(False, token=token, key='pause-key')
        self.assertFalse(self.access.settings(True, token=token, key='enable-key')['observation_enabled'])
        with self.assertRaises(AccessError):
            self.access.settings(False, token=token, key='enable-key')

    def test_reissued_code_cannot_duplicate_or_reactivate_pairing(self):
        token = self.access.exchange(self.access.issue_code('dashboard')['code'], self.web)['token']
        original = self.access.paired_code(token, 'first-key', 'extension')['code']
        self.assertEqual(original, self.access.paired_code(token, 'first-key', 'extension')['code'])
        self.access.exchange(original, self.extension)
        with self.assertRaises(AccessError):
            self.access.paired_code(token, 'first-key', 'extension')
        self.assertNotIn(original.encode(), self.access.path.read_bytes())
