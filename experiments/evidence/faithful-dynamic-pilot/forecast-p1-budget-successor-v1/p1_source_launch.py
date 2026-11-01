"""One-shot P1 BEA evidence capture. Status and model calls are excluded."""
import json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-p1-budget-successor-v1'))
import p1_retry as r
import p1_budget as p
import retry_accounting_launch as a
CONTRACT=ROOT/'forecast-cpi-p1-source-contract-20261029-v2.json'
PACKET=ROOT/'forecast-cpi-p1-source-challenge-packet-v2.json'
RECEIPT=ROOT/'forecast-cpi-p1-source-challenge-receipt-v2.json'
OUTPUT=ROOT/'forecast-cpi-p1-event-results-20261029-01'
ACCOUNT_SHA='9e461fe6df6cfd05aabab675d4f366b4bf9843bccd138ad005f60b7c313d4f89'
SOURCE_SHA='eea71b32f48b997cce6784b3563e02a336736b2b4a4fb10de2cae38d26cd628a'
PRICE_SHA='b74616e0044807e22c9d3cc65eeaf853aa78d97ece9188de6c80d55e89e586d3'
FILES=('forecast-p1-budget-successor-v1/p1_source_launch.py','forecast-p1-budget-successor-v1/p1_retry.py','forecast-p1-budget-successor-v1/p1_budget.py','forecast-p1-budget-successor-v1/retry_accounting_launch.py','forecast-budget-v1/forecast_ledger.py','budget-v2/ledger.py','transport/oneshot.py')

def verify(expected):
 cr,pr,rr=map(p.read,(CONTRACT,PACKET,RECEIPT));c,w,receipt=map(json.loads,(cr,pr,rr));d=w.get('internal_digest')
 if expected!=SOURCE_SHA or p.digest(cr)!=expected or c.get('schema')!='cpi-p1-source-contract-v1' or c.get('status')!='frozen' or c.get('account_contract_sha256')!=ACCOUNT_SHA or c.get('caps')!=p.CAPS or c.get('no_retry') is not True or c.get('no_canary') is not True or c.get('price_observation_sha256')!=PRICE_SHA or p.digest(Path(r.__file__).read_bytes())!=c.get('retry_bridge_sha256') or p.digest(Path(p.__file__).read_bytes())!=c.get('bridge_sha256'):raise p.Error('source frozen binding mismatch')
 if w.get('schema_version')!='eval_contract_challenge_packet_v1' or w.get('overall_state')!='ready' or w.get('witness',{}).get('identity')!='cpi_p1_source_witness' or w.get('witness',{}).get('mode')!='read_only_offline' or w.get('challenged_contract',{}).get('raw_sha256')!=expected or d!=p.digest(p.canonical({k:v for k,v in w.items() if k!='internal_digest'})) or receipt.get('packet_raw_sha256')!=p.digest(pr) or receipt.get('packet_byte_count')!=len(pr) or receipt.get('packet_internal_digest')!=d or receipt.get('state')!='ready':raise p.Error('source independent review mismatch')
 observed=w.get('context_binding',{}).get('code_bindings_at_inspection',{})
 for name in FILES:
  raw=p.read(ROOT/name);h=p.digest(raw)
  if observed.get(name)!={'sha256':h,'size':len(raw)}:raise p.Error('source code changed after challenge')
 ops=c.get('operations');expected_url='https://www.bea.gov/news/2026/personal-income-and-outlays-september-2026'
 if not isinstance(ops,list) or len(ops)!=9 or ops[0].get('kind')!='event' or ops[0].get('ticket',{}).get('id')!='p1-cpi-bea-fetch' or ops[0].get('payload')!={'api':'linkup','path':'/fetch','body':{'url':expected_url},'query':{}}:raise p.Error('event payload mismatch')
 for n,op in enumerate(ops[1:],1):
  if op.get('kind')!='status_refresh' or op.get('ticket',{}).get('id')!=f'p1-cpi-status-{n:02d}' or op.get('payload')!={'api':'kalshi','path':'/markets','body':{},'query':{'tickers':'KXCPI-26OCT-T0.2'}}:raise p.Error('status scope mismatch')
 if p.digest(p.read(ROOT/'forecast-cpi-p1-source-ui-prices-20261029-v2.json'))!=PRICE_SHA or p.digest(p.read(Path(c['event_observation_path'])))!=c['event_observation_sha256']:raise p.Error('source evidence changed')
 a.verify(ACCOUNT_SHA)
 return c,cr,pr,rr

def put(path,raw):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())

def execute(expected):
 """One exact event request; caller separately validates eligibility afterward."""
 c,cr,pr,rr=verify(expected)
 if Path.cwd().resolve()!=ROOT or OUTPUT.exists():raise p.Error('unsafe source output destination')
 def reviewed_account(raw):
  try:return a.verify(ACCOUNT_SHA)[1]==raw
  except Exception:return False
 def reviewed_source(raw):
  try:return verify(expected)[1]==raw
  except Exception:return False
 def ticket_valid(ticket,raw):return reviewed_source(cr) and any(x['ticket']==ticket and p.canonical(x['payload'])==raw for x in c['operations'])
 account=r.reopen(a.LEDGER,contract_path=a.CONTRACT,contract_sha=ACCOUNT_SHA,verify_challenge=reviewed_account)
 try:
  stage=r.activate_source(account,stage_path=CONTRACT,stage_sha=expected,verify_challenge=reviewed_source,verify_ticket=ticket_valid)
  OUTPUT.mkdir(mode=0o700)
  put(OUTPUT/'started.json',p.canonical({'contract_sha256':expected,'challenge_sha256':p.digest(pr),'challenge_receipt_sha256':p.digest(rr),'id':'p1-cpi-bea-fetch'}))
  def token(provider):
   if provider!='orthogonal':raise p.Error('model denied')
   v=subprocess.run(['/usr/bin/security','find-generic-password','-s','com.maguire.orthogonal.live','-a','maguire','-w'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False,timeout=15)
   if v.returncode or not v.stdout.strip():raise p.Error('credential unavailable')
   return v.stdout.strip().decode('ascii')
  sys.path.insert(0,str(ROOT/'transport'));from oneshot import OneShotTransport
  op=c['operations'][0];raw=stage.source(op['ticket']['id'],'orthogonal','/v1/run',p.canonical(op['payload']),op['ticket'],OneShotTransport('source-only-123',token));rec=stage.receipt(op['ticket']['id']);put(OUTPUT/'event.raw.json',raw)
  if rec['actual_micro']>10000:stage.stop('fetch billed above observed UI price');raise p.Error('fetch price above observed UI')
  result={'schema':'cpi-p1-event-capture-v1','status':'captured_not_yet_eligible','contract_sha256':expected,'source_id':op['ticket']['id'],'receipt':{k:rec[k] for k in ('id','http_status','request_hash','response_hash','actual_micro','started_at_utc','completed_at_utc')},'ledger':account.summary(),'qualification':'Source capture only; verify event content, first-availability assumption, and active market before any model calls.'};put(OUTPUT/'summary.json',p.canonical(result));return result
 except BaseException:
  if not account.base.summary()['stopped']:account.base.stop('P1 event source capture failed; no retry')
  raise
 finally:account.close()
