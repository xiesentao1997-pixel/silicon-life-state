"""Trusted desktop launcher discovery for the running installation."""
import hashlib
import hmac
import json
import secrets
import os
import uuid
from contextlib import contextmanager
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from urllib.parse import urlencode


def endpoint_proof(key, port, challenge):
    payload = f"sls-local-launcher-v1:{port}:{challenge}".encode('ascii')
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


@contextmanager
def publish_endpoint(data_dir, server):
    path = Path(data_dir) / 'service-endpoint.json'
    staging = path.with_name('.service-endpoint-' + uuid.uuid4().hex)
    try:
        fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'port': server.server_port, 'verifier': server.launch_key.hex()}, stream)
        os.replace(staging, path)
        yield
    finally:
        staging.unlink(missing_ok=True)
        path.unlink(missing_ok=True)


def existing_endpoint(data_dir):
    """Never send a pairing code in an HTTP request or to an unverified port."""
    conn = None
    try:
        entry = json.loads((Path(data_dir) / 'service-endpoint.json').read_text(encoding='utf-8'))
        port = entry['port']
        verifier = bytes.fromhex(entry['verifier'])
        if type(port) is not int or not 0 < port <= 65535 or len(verifier) != 32:
            return None
        conn = HTTPConnection('127.0.0.1', port, timeout=2)
        challenge = secrets.token_hex(32)
        conn.request('GET', '/api/health', headers={'X-SLS-Reconnect-Challenge': challenge})
        res = conn.getresponse()
        if res.status != 200:
            return None
        reply = json.loads(res.read(8192))
        proof = reply.get('reconnect_proof') if isinstance(reply, dict) else None
        if isinstance(proof, str) and hmac.compare_digest(proof, endpoint_proof(verifier, port, challenge)):
            return f'http://127.0.0.1:{port}'
    except (OSError, ValueError, KeyError, TypeError, HTTPException):
        pass
    finally:
        if conn is not None:
            conn.close()
    return None


def bundle(access, base, reconnect=False):
    dashboard = access.issue_code('dashboard')
    extension = access.issue_code('extension')
    fragment = {'pair': dashboard['code']}
    if reconnect:
        fragment.update({'view':'settings', 'action':'pair-extension', 'extension_code':extension['code']})
    return {'base_url': base, 'dashboard_url': base + '/#' + urlencode(fragment),
            'code': dashboard['code'], 'extension_code': extension['code'],
            'extension_expires_at': extension['expires_at'], 'server_time': extension['server_time']}
