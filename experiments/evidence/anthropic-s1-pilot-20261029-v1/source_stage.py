"""One bounded source read. Prepare freezes scope; execute requires review."""
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import runtime

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def save(path, data):
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2).encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(raw); out.flush(); os.fsync(out.fileno())
    fd = os.open(ROOT, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)
    return digest(raw)

def sha(path):
    return digest(path.read_bytes())

def prepare():
    if (ROOT / 'ledger').exists(): raise ValueError('ledger already exists')
    price = {'schema':'observed-source-price-v1','endpoint':'serper POST /news',
             'catalog_url':'https://www.orthogonal.com/dashboard/discover/serper/91fb13eb-b5bd-4602-849f-a87d7df01e75',
             'observed':'$0.0020 per call, displayed in authenticated Orthogonal catalog',
             'observed_date':'2026-10-29','evidence_type':'human-readable browser observation; not a binding provider quote'}
    price_sha = save(ROOT/'source-price.json', price)
    contract = {'schema':'anthropic-s1-source-contract-v1',
        'scope':'one source discovery read, then freeze complete inputs for separate model challenge',
        'request':{'api':'serper','path':'/news','body':{'q':'Anthropic IPO S-1 compute obligations governance','num':3},'query':{}},
        'source_max_attempts':1,'source_reserve_micro':10000,'source_list_price_micro':2000,
        'previous_exposure_micro':56609714,'cumulative_cap_micro':60000000,
        'on_uncertain':'stop, retain reservation; no retry','source_price_sha256':price_sha,
        'predecessor':runtime.predecessor_snapshot(),
        'code_sha256':{'runtime.py':sha(ROOT/'runtime.py'), 'source_stage.py':sha(ROOT/'source_stage.py')},
        'prepared_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
    save(ROOT/'source-contract.json', contract)
    print('source contract prepared', sha(ROOT/'source-contract.json'), flush=True)

def execute():
    contract = json.loads((ROOT/'source-contract.json').read_bytes())
    check = json.loads((ROOT/'source-challenge.json').read_bytes())
    if check.get('status') != 'ready' or check.get('contract_sha256') != sha(ROOT/'source-contract.json') or check.get('blockers') != []:
        raise ValueError('independent source challenge not ready')
    if contract['predecessor'] != runtime.predecessor_snapshot() or contract['source_price_sha256'] != sha(ROOT/'source-price.json'):
        raise ValueError('source contract drift')
    for file, expected in contract['code_sha256'].items():
        if sha(ROOT/file) != expected: raise ValueError('source code drift')
    if any((ROOT/x).exists() for x in ('ledger','source-dispatch.json','source-summary.json')):
        raise ValueError('source operation already started')
    save(ROOT/'source-dispatch.json', {'contract_sha256':sha(ROOT/'source-contract.json'),
         'challenge_sha256':sha(ROOT/'source-challenge.json'),'started_utc':dt.datetime.now(dt.timezone.utc).isoformat()})
    run = runtime.Runtime(ROOT/'ledger', transport=runtime.build_live_transport())
    try:
        raw = run.fetch_serper_news(price_evidence_sha256=sha(ROOT/'source-price.json'), transport=runtime.build_source_transport())
        result = json.loads(raw)
        save(ROOT/'serper-news-response.json', result)
        receipt = run.ledger.receipt('source:s1:serper-news:001')
        save(ROOT/'source-summary.json', {'state':receipt['state'], 'http_status':receipt['http_status'],
             'request_sha256':receipt['request_hash'], 'response_sha256':receipt['response_hash'],
             'started_at_utc':receipt['started_at_utc'],'completed_at_utc':receipt['completed_at_utc'],
             'actual_micro':receipt['actual_micro'], 'exposure':run.summary(),
             'note':'source candidates only; not verified truth'})
        print('source captured', json.dumps(run.summary()), flush=True)
    except Exception as exc:
        if not run.ledger.summary()['stopped']: run.ledger.stop('source capture failure; no repeat')
        save(ROOT/'source-summary.json', {'state':'failed_or_uncertain','exception_type':type(exc).__name__,
              'exposure':run.summary(),'note':'review ledger; no automatic retry'})
        raise
    finally:
        run.close()

if __name__ == '__main__':
    {'prepare':prepare, 'execute':execute}[sys.argv[1]]()
