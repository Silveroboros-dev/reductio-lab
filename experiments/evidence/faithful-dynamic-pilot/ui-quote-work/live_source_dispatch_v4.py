"""Explicit launcher for seven remaining authorized source reads; no action on import.

Do not execute until the separately bound source contract and independent
challenge are complete. No tokens or account/project names are printed.
"""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for directory in (ROOT/'budget-v2', ROOT/'ui-quote-work', ROOT/'source-successor'):
    sys.path.insert(0, str(directory))
import bridge
import source_capture_v4 as source_capture

PRICE_SHA='bb22abd1885a58a5fd317c5167baa1b70621dae6642343cb6c5fd341ca5ab6ac'
CHALLENGE_WITNESS='audit_go'

def digest(x): return hashlib.sha256(x).hexdigest()

def verify_ui(raw):
    if digest(raw)!=PRICE_SHA: return False
    x=json.loads(raw)
    return (x.get('url')==source_capture.ui_quote.URL and x.get('reported_rate')=='$0.002 per call'
            and x.get('credential_identity')=='Keychain configured credential suffix matches default dashboard key, checked in memory without displaying credential')

def verify_challenge(packet_bytes, receipt_bytes, contract_bytes):
    p=json.loads(packet_bytes);r=json.loads(receipt_bytes);c=json.loads(contract_bytes)
    return (p.get('overall_state')=='ready' and p.get('witness',{}).get('identity')==CHALLENGE_WITNESS
            and p.get('witness',{}).get('mode')=='read_only_offline'
            and p.get('challenged_contract',{}).get('raw_sha256')==digest(contract_bytes)
            and r.get('packet_raw_sha256')==digest(packet_bytes)
            and r.get('packet_byte_count')==len(packet_bytes)
            and c.get('status')=='frozen')

def keychain_token(provider):
    if provider!='orthogonal': raise ValueError('source phase permits only Orthogonal')
    r=subprocess.run(['/usr/bin/security','find-generic-password','-s','com.maguire.orthogonal.live','-a','maguire','-w'],
                     stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False)
    token=r.stdout.strip()
    if r.returncode!=0 or not token or not token.endswith(b'W6Gj'):
        raise RuntimeError('configured credential does not match observed account identity')
    return token.decode('ascii')

def project_id():
    import google.auth
    _, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    if not project: raise RuntimeError('project unavailable')
    return project

def dispatch(contract_path,challenge_path,receipt_path,ledger_root,output_root, *, ledger):
    # Caller supplies a create-only PhaseLedger made by verified bridge; no network.
    if not isinstance(ledger,bridge.PhaseLedger) or Path(ledger_root).resolve()!=ledger.root.resolve():
        raise ValueError('verified successor ledger and exact root required')
    try:
        return source_capture.execute(contract_path,challenge_path,receipt_path,output_root,
            ledger=ledger,verify_challenge=verify_challenge,verify_ui=verify_ui,
            project_id_provider=project_id,token_provider=keychain_token)
    finally: ledger.close()

# No __main__: an explicit, audited caller must invoke dispatch().
