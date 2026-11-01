"""Read-only verification of the captured BEA source; no network or mutation."""
import copy,json,sqlite3,re
from pathlib import Path
import gate,conditional_news
ROOT=Path(__file__).resolve().parent.parent
SOURCE_CONTRACT_SHA='eea71b32f48b997cce6784b3563e02a336736b2b4a4fb10de2cae38d26cd628a'
RAW_SHA='f3cd83fafc54825f6310d29b34bfd7d830a8c914365d55d6c1b30037e59919d2'
REQUEST_SHA='1263ad9e1ebc53fbaaaa6e243ed693357a2fd7e5a7275555d4f8189ed353fdab'
DB=ROOT/'forecast-cpi-p1-retry-ledger-20261029-01/ledger.sqlite3'
RAW=ROOT/'forecast-cpi-p1-event-results-20261029-01/event.raw.json'
SUMMARY=ROOT/'forecast-cpi-p1-event-results-20261029-01/summary.json'
CONTRACT=ROOT/'forecast-cpi-p1-source-contract-20261029-v2.json'
class Error(ValueError):pass

def receipt():
 db=sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
 try:r=db.execute("select * from effects where id='p1-cpi-bea-fetch'").fetchone()
 finally:db.close()
 if r is None:raise Error('no event receipt')
 return dict(r)

def verify_fetch(raw,r,obs):
 try:
  if gate.sha(raw)!=RAW_SHA or RAW.read_bytes()!=raw or gate.sha(CONTRACT.read_bytes())!=SOURCE_CONTRACT_SHA:return False
  row=receipt();summary=json.loads(SUMMARY.read_bytes());contract=json.loads(CONTRACT.read_bytes())
  if any(row.get(k)!=r.get(k) for k in ('id','kind','state','http_status','request_hash','response_hash','actual_micro','response','started_at_utc','completed_at_utc')):return False
  op=contract['operations'][0];expected=gate.canonical(op['payload'])
  if (op['kind'],op['ticket']['id'],op['payload']['body']['url'],row['request_hash'],row['actual_micro'])!=('event','p1-cpi-bea-fetch',conditional_news.URL,REQUEST_SHA,10000) or bytes(row['request'])!=expected or gate.sha(expected)!=REQUEST_SHA:return False
  if (summary['contract_sha256'],summary['receipt']['response_hash'],summary['receipt']['completed_at_utc'])!=(SOURCE_CONTRACT_SHA,RAW_SHA,row['completed_at_utc']):return False
  parsed=json.loads(raw);txt=parsed['data']['markdown']
  if parsed.get('success') is not True or parsed.get('priceCents')!=1 or parsed['billing']['chargedPriceCents']!=1:return False
  required=['EMBARGOED UNTIL RELEASE AT 8:30 a.m. EDT, Thursday, October 29, 2026','BEA 26–46','Personal Income and Outlays, September 2026','PCE price index** for September increased 0.5 percent','PCE price index increased 0.3 percent','PCE price index** for September increased 3.6 percent','PCE price index increased 3.1 percent from one year ago']
  if any(s not in txt for s in required):return False
  if obs.get('values')!={'pce_monthly_percent':0.5,'pce_yearly_percent':3.6,'core_pce_monthly_percent':0.3,'core_pce_yearly_percent':3.1}:return False
  return True
 except (OSError,ValueError,KeyError,TypeError,sqlite3.Error):return False

def candidate(*,verify_amendment):
 raw=RAW.read_bytes();r=receipt()
 return conditional_news.make(raw=raw,receipt=r,verify_amendment=verify_amendment,verify_fetch=verify_fetch)
