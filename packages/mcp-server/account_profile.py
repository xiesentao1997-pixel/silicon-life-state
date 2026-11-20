"""Select a local Codex profile partition. Authentication remains the owner-issued grant."""
import base64
import hashlib
import json
from pathlib import Path


def account_binding(home):
    """Read identifiers from the host's local file-backed sign-in. Never return token data."""
    try:
        with (Path(home) / 'auth.json').open(encoding='utf-8') as f:
            raw = f.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            return None
        data = json.loads(raw)
        if data.get('auth_mode') not in (None, 'chatgpt'):
            return None
        tokens = data['tokens']
        workspace = tokens['account_id']
        payload = tokens['id_token'].split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        parts = ['codex', claims['iss'], claims['sub'], workspace]
        if not all(isinstance(x, str) and 0 < len(x) <= 512 for x in parts):
            return None
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError):
        return None
    return 'acct_' + hashlib.sha256(json.dumps(parts,ensure_ascii=True).encode()).hexdigest()
