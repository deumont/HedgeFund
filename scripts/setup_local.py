"""Idempotent local installation bootstrap. Never prints a credential."""
import hashlib
import secrets
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.config import Settings
from backend.db import DB
from backend.catalog import seed


def password_hash(password,salt=None):
    salt=salt or secrets.token_hex(16)
    digest=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
    return salt+':'+digest


def setup():
    env=ROOT/'.env'
    if not env.exists():
        password=secrets.token_urlsafe(18)
        content=(ROOT/'.env.example').read_text(encoding='utf-8')
        content+='\nSESSION_SECRET='+secrets.token_hex(32)+'\nCEO_PASSWORD_HASH='+password_hash(password)+'\n'
        env.write_text(content,encoding='utf-8')
        (ROOT/'local-access.txt').write_text('ATLAS — lokaler Zugang\nAdresse: http://127.0.0.1:8765\nBenutzer: CEO\nPasswort: '+password+'\n\nDiese Datei nicht weitergeben. API-Schlüssel ausschließlich in .env eintragen.\n',encoding='utf-8')
    cfg=Settings()
    db=DB(cfg.database_path)
    db.init()
    seed(db)
    # Explicit Start.cmd clears a previous manual stop request; not called by watchdog restarts.
    db.set('supervisor_paused',False)
    print('Lokale Datenbank initialisiert: 100 Agenten, 25 Demo-Ledgers, 3.000-EUR-Fonds. Zugang in local-access.txt.')


if __name__=='__main__':
    setup()
