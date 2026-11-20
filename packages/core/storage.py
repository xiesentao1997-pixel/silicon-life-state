"""Local SQLite connection, process lock, online backup and verified recovery."""
import contextlib
import os
import re
import secrets
import sqlite3
import threading
from pathlib import Path

from .validation import canonical, digest, fail

SCHEMA = 2
MIGRATIONS = Path(__file__).with_name('migrations')
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def event_hash(ev):
    keys = ('event_id','subject_id','instance_id','session_id','type','source','actor','created_at',
            'payload','related','model_version','adapter_version','prev_hash','version','seq')
    # SQL TEXT payload and related are canonical serialized JSON.
    return digest(canonical({key:ev[key] for key in keys}))


def verify_db(conn, *, allow_legacy=False):
    errors = []
    if conn.execute('PRAGMA user_version').fetchone()[0] not in ((1, SCHEMA) if allow_legacy else (SCHEMA,)):
        errors.append('Unsupported schema version.')
    check = conn.execute('PRAGMA integrity_check').fetchall()
    if [r[0] for r in check]!=['ok']:
        errors.append('SQLite integrity check failed.')
    if conn.execute('PRAGMA foreign_key_check').fetchone():
        errors.append('Foreign key integrity check failed.')
    tips, count = {}, 0
    for ev in conn.execute('SELECT * FROM events ORDER BY seq'):
        prev,version = tips.get(ev['session_id'],('',0))
        if (ev['prev_hash']!=prev or ev['version']!=version+1 or event_hash(ev)!=ev['hash']):
            errors.append('Event chain mismatch: '+ev['event_id'])
            break
        tips[ev['session_id']] = (ev['hash'],ev['version'])
        count += 1
    return {'ok':not errors,'events':count,'errors':errors}


def migrate(conn):
    version = conn.execute('PRAGMA user_version').fetchone()[0]
    if version > SCHEMA:
        fail('FUTURE_SCHEMA','Database belongs to a newer version.',409)
    scripts = ('001_initial.sql', '002_installations.sql')
    for filename in scripts[version:]:
        sql = (MIGRATIONS / filename).read_text(encoding='utf-8')
        conn.executescript('BEGIN IMMEDIATE;\n' + sql + '\nCOMMIT;')


class Files:
    def __init__(self, home):
        self.home = Path(home).expanduser().resolve()
        self.home.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.path = self.home/'state.sqlite3'
        self.backups = self.home/'backups'
        self.backups.mkdir(mode=0o700,exist_ok=True)
        self.lockpath = self.home/'store.lock'
        self.pending_erasure = self.home/'erasure.pending'
        with _LOCKS_GUARD:
            self.thread_lock = _LOCKS.setdefault(str(self.home),threading.RLock())
        with self.lock():
            self.key = self._install_key()

    def _install_key(self):
        path = self.home/'issuance.key'
        if not path.exists():
            temporary = self.home/'issuance.key.tmp'
            with open(temporary,'wb',opener=lambda p,f:os.open(p,f,0o600)) as f:
                f.write(secrets.token_bytes(32))
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary,path)
        key = path.read_bytes()
        if len(key)!=32:
            fail('INVALID_INSTALLATION','Credential issuance key is damaged.',503)
        return key

    @contextlib.contextmanager
    def lock(self):
        # Coordinate filesystem replacement and data deletion with all live stdio
        # and HTTP writers, including separate OS processes using this home.
        with self.thread_lock, open(self.lockpath,'a+b') as lockfile:
            if os.name=='nt':
                import msvcrt
                if lockfile.tell()==0:
                    lockfile.write(b'\0')
                    lockfile.flush()
                lockfile.seek(0)
                msvcrt.locking(lockfile.fileno(),msvcrt.LK_LOCK,1)
                try:
                    yield
                finally:
                    lockfile.seek(0)
                    msvcrt.locking(lockfile.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(lockfile,fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lockfile,fcntl.LOCK_UN)

    @contextlib.contextmanager
    def connect(self):
        # Laziness allows list_backups/restore even if the live database is corrupt.
        self.path.touch(mode=0o600,exist_ok=True)
        conn = sqlite3.connect(self.path,timeout=15,isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA busy_timeout=15000')
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('PRAGMA trusted_schema=OFF')
            conn.execute('PRAGMA secure_delete=ON')
            conn.execute('PRAGMA synchronous=FULL')
            conn.execute('PRAGMA journal_mode=WAL')
            migrate(conn)
            if self.pending_erasure.exists():
                self.finish_erasure(conn)
            yield conn
        finally:
            conn.close()

    def mark_erasure(self):
        # Only a flag lives here: never a session ID or original state. This is
        # durable before SQLite's commit, so a restart can finish the scrub.
        with open(self.pending_erasure,'wb',opener=lambda p,f:os.open(p,f,0o600)) as file:
            file.write(b'pending')
            file.flush()
            os.fsync(file.fileno())
        if os.name!='nt':
            fd=os.open(self.home,os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def finish_erasure(self,conn):
        if not self.pending_erasure.exists():
            return
        def truncate():
            busy,_,_=conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
            if busy:
                fail('DATABASE_BUSY','A database reader is delaying journal erasure. Retry after closing it.',503)
        truncate()
        conn.execute('VACUUM')
        truncate()
        self.pending_erasure.unlink(missing_ok=True)

    def backup_path(self, backup_id):
        if not isinstance(backup_id,str) or not re.fullmatch(r'bak_[a-f0-9]{32}',backup_id):
            fail('INVALID_BACKUP','Invalid managed backup ID.')
        return self.backups/(backup_id+'.sqlite3')

    def clean_temporary(self):
        # An interrupted operation may have left an incomplete copy. No other
        # operation can be using these under the exclusive installation lock.
        for path in (self.home/'recovery.tmp',self.backups/'backup.tmp',self.backups/'signature.tmp'):
            for suffix in ('','-shm','-wal','-journal'):
                Path(str(path)+suffix).unlink(missing_ok=True)

    def purge_backups(self):
        self.clean_temporary()
        count=0
        for path in self.backups.glob('bak_*.sqlite3'):
            path.unlink()
            count+=1
        for path in self.backups.glob('bak_*.sig'):
            path.unlink()
        return count
