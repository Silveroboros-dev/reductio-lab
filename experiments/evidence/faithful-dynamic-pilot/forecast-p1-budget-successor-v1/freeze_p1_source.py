"""Freeze CPI P1 event + eight status operations. No provider calls.

Requires independently observed official BEA URL and a local evidence file.
An operator and independent challenge must check the evidence; this script
cannot establish that the event actually occurred or the webpage is correct.
"""
import datetime as dt, json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-p1-budget-successor-v1'))
import p1_retry as r
import p1_budget as p
ACCOUNT_SHA='9e461fe6df6cfd05aabab675d4f366b4bf9843bccd138ad005f60b7c313d4f89'
PRICE='forecast-cpi-p1-source-ui-prices-20261029-v1.json'
PRICE_SHA='e7558296c75c7008692dc1dd0f7dde3fd13400be8fd28014305da7ea3c1f3c3c'
OUT=ROOT/'forecast-cpi-p1-source-contract-20261029-v1.json'

def freeze(url, event_evidence):
 if Path.cwd().resolve()!=ROOT or OUT.exists():raise p.Error('wrong context or existing contract')
 if not isinstance(url,str) or not url.startswith('https://www.bea.gov/') or '#' in url:raise p.Error('official BEA URL required')
 ep=Path(event_evidence)
 if not ep.is_absolute() or not ep.is_file():raise p.Error('event observation artifact required')
 eraw=ep.read_bytes();ev=json.loads(eraw)
 if ev.get('official_url')!=url or ev.get('published') is not True or ev.get('source')!='BEA official page' or not ev.get('observed_at_utc'):raise p.Error('event observation incomplete')
 raw=p.read(ROOT/PRICE,PRICE_SHA);observed=json.loads(raw)['observed_at_utc'];expiry=dt.datetime.fromisoformat(observed.replace('Z','+00:00'))+dt.timedelta(minutes=15)
 if dt.datetime.now(dt.timezone.utc)>=expiry:raise p.Error('source price evidence expired')
 receipt=json.loads(p.read(ROOT/'forecast-cpi-p1-retry-accounting-receipt-20261029.json'))
 if receipt.get('contract_sha256')!=ACCOUNT_SHA or receipt.get('ledger',{}).get('source_attempts')!=19:raise p.Error('account receipt mismatch')
 parent=r.inspect_parent()
 event={'api':'linkup','path':'/fetch','body':{'url':url},'query':{}}
 status={'api':'kalshi','path':'/markets','body':{},'query':{'tickers':'KXCPI-26OCT-T0.2'}}
 operations=[]
 for ident,kind,category,payload in [('p1-cpi-bea-fetch','event','fetch',event)]+[(f'p1-cpi-status-{n:02d}','status_refresh','market',status) for n in range(1,9)]:
  ticket={'id':ident,'provider':'orthogonal','endpoint':'/v1/run','request_sha256':p.digest(p.canonical(payload)),'max_micro':150000,'evidence_sha256':PRICE_SHA,'expires_utc':expiry.isoformat(),'category':category,'settlement':'orthogonal_price_cents'}
  operations.append({'ticket':ticket,'payload':payload,'kind':kind})
 c={'schema':'cpi-p1-source-contract-v1','status':'frozen','account_contract_sha256':ACCOUNT_SHA,'caps':p.CAPS,'case_id':'case-02','cpi_receipt_sha256':parent['cpi_receipt_sha256'],'no_retry':True,'no_canary':True,'bridge_sha256':p.digest(Path(p.__file__).read_bytes()),'retry_bridge_sha256':p.digest(Path(r.__file__).read_bytes()),'event_observation_path':str(ep),'event_observation_sha256':p.digest(eraw),'price_observation_sha256':PRICE_SHA,'operations':operations,'qualification':'The event is used only after independent inspection of the returned evidence and strict no-news isolation. Each market status is an independent observation; unused calls are not executed. Source 429 and ambiguous effects do not retry.'}
 out=p.canonical(c);fd=os.open(OUT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f:f.write(out);f.flush();os.fsync(f.fileno())
 return {'contract':str(OUT),'sha256':p.digest(out),'expires_utc':expiry.isoformat(),'operations':len(operations)}
if __name__=='__main__':
 if len(sys.argv)!=3:raise SystemExit('usage: freeze_p1_source.py BEA_URL /absolute/path/to/observed-event.json')
 print(freeze(sys.argv[1],sys.argv[2]))
