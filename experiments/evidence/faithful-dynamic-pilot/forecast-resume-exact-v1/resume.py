"""Offline reconstruction of exact three 429-interrupted P0 branches.

No provider client, credentials, SQLite writes, side effects or authority.
An independently reviewed caller must supply a lineage-checked, journalled
callback that performs the one bounded retry or previously unstarted operation,
and a create-only durable recorder. Imported historical count receipts must
be validated and linked by that callback; a new count must not be issued for
the three failed operations. Local clock values alone do not prove status,
truth, timing of news, or model-version stability.
"""
from __future__ import annotations
import copy, hashlib, json, sqlite3, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-controller-v1'))
import forecast

CONFIG={
 'case-01':{'arm':'b','failed':2,'db':'forecast-recovery-ledger-20261029-01/ledger.sqlite3','db_sha':'ed9d2aad306864dd228c85ffe3fc4ddc092f6b3b2272139bb12743893de72de7','input':'forecast-p0-results-20261029-01/00-p0-input.json','input_sha':'511fdbbf1cc4e5074e45168f4d37892d272c9b5aa3a568196054aa0ce79dcd43','c':'forecast-p0-results-20261029-01/00-p0-c.json','c_sha':'e7467c953c0f54a9f0e90b500f17896ecb2493339aedfe4f4c9061e55af07a56'},
 'case-02':{'arm':'b','failed':5,'db':'forecast-429-recovery-ledger-20261029-01/ledger.sqlite3','db_sha':'ee8670dbc34721e39aecaf4b8fe160e38e56af53a772872b323bcef05739a02b','input':'forecast-p0-remaining-results-20261029-01/00-p0-input.json','input_sha':'849dd5b06474ab90a200b0d2282f4b788e452f44f5a0857783b9fe1ee9647575','c':'forecast-p0-remaining-results-20261029-01/00-p0-c.json','c_sha':'e8f37e1eeb1d559feead828ad31a904ba9c5cfda9ca9786e3e9527f3f4e3b1e3'},
 'case-04':{'arm':'c','failed':3,'db':'forecast-429b-recovery-ledger-20261029-01/ledger.sqlite3','db_sha':'fe936ec04125fa108e321a7429788caede980630e1566354353c19e46f81d677','input':'forecast-p0-final-two-results-20261029-01/01-p0-input.json','input_sha':'4ff3c245beacd495943c14d0279666a28704fc190cb0bebd34e2dd68dcfc5618','c':None,'c_sha':None},
}
FORECAST_SHA='596ee6fdc840977a4697536b0307585e79cadfcfb0b962225c0feb06a7e79b2f'
DEADLINE=datetime(2026,10,29,12,30,tzinfo=timezone.utc)
class Error(ValueError):pass
class Reached429(Exception):pass

def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def read_rel(rel,expected):
 p=ROOT/rel
 if p.is_symlink() or p.resolve()!=p.absolute() or not p.is_file():raise Error('unsafe input')
 raw=p.read_bytes()
 if sha(raw)!=expected:raise Error('historical input changed: '+rel)
 return raw

def inspect(case):
 """Read verified historical rows only; return frozen bindings and bytes."""
 if case not in CONFIG:raise Error('unknown case')
 read_rel('forecast-controller-v1/forecast.py',FORECAST_SHA)
 cfg=CONFIG[case];read_rel(cfg['db'],cfg['db_sha'])
 prepared=json.loads(read_rel(cfg['input'],cfg['input_sha']))
 if prepared.get('case',{}).get('case_id')!=case or prepared.get('task',{}).get('case_id')!=case:raise Error('case mismatch')
 oldc=json.loads(read_rel(cfg['c'],cfg['c_sha'])) if cfg['c'] else None
 if oldc is not None and (oldc.get('calls')!=8 or oldc.get('status') not in ('proposal','unknown','technical_failure')):raise Error('historical C mismatch')
 db=sqlite3.connect('file:'+str(ROOT/cfg['db'])+'?mode=ro',uri=True)
 try:
  if db.execute('SELECT stopped FROM run').fetchone()!=(1,):raise Error('predecessor not stopped')
  records=[]
  for n in range(1,cfg['failed']+1):
   ident=f'p0:{case}:{cfg["arm"]}:{n:02d}'
   row=db.execute('SELECT request,request_hash,http_status,response,response_hash,related_id FROM effects WHERE id=? AND kind="generation"',('generation:'+ident,)).fetchone()
   count=db.execute('SELECT request,request_hash,http_status,response,response_hash,actual_micro FROM effects WHERE id=? AND kind="count"',('count:'+ident,)).fetchone()
   if row is None or count is None:raise Error('missing effect')
   req,rh,status,resp,sh,related=row;creq,ch,cs,cresp,csh,charge=count
   if sha(bytes(req))!=rh or sha(bytes(resp))!=sh or bytes(creq)!=bytes(req) or ch!=rh or sha(bytes(cresp))!=csh or cs!=200 or charge!=0 or related!='count:'+ident:raise Error('receipt mismatch')
   if status!=(429 if n==cfg['failed'] else 200):raise Error('unexpected prior status')
   count_value=json.loads(cresp).get('totalTokens')
   if type(count_value) is not int or not 0<=count_value<=16384:raise Error('invalid historic token count')
   if status==429:
    err=json.loads(resp).get('error',{})
    if err.get('code')!=429 or err.get('status')!='RESOURCE_EXHAUSTED':raise Error('nonmatching 429 response')
   records.append({'id':'generation:'+ident,'count_id':'count:'+ident,'request':bytes(req),'request_sha256':rh,'response':bytes(resp),'response_sha256':sh,'count_response_sha256':csh,'status':status})
  # No previously attempted effect in remainder of this case, including B on case04.
  prefixes=['generation:p0:'+case+':'+cfg['arm']+':']
  if case=='case-04':prefixes.append('generation:p0:case-04:b:')
  got=[row[0] for row in db.execute('SELECT id FROM effects WHERE kind="generation"') if any(row[0].startswith(p) for p in prefixes)]
  if set(got)!={x['id'] for x in records}:raise Error('unexpected previously attempted operation')
 finally:db.close()
 return {'case_id':case,'case':prepared['case'],'task':prepared['task'],'prior_c':oldc,'records':records,'db_sha256':cfg['db_sha']}

def _replayer(snapshot,*,generate=None,verify_live=None):
 records=snapshot['records'];case=snapshot['case_id'];cfg=CONFIG[case];n=0;retried=False
 def run(stage,payload):
  nonlocal n,retried
  n+=1;request=forecast.build_request(stage,payload);raw=canonical(request)
  if n<=len(records):
   x=records[n-1]
   if raw!=x['request'] or sha(raw)!=x['request_sha256']:raise Error('reconstructed request differs from original')
   if x['status']==200:return forecast.parse_response(json.loads(x['response']))
   if n!=cfg['failed'] or retried:raise Error('retry policy mismatch')
   if generate is None:raise Reached429(stage)
   binding={'kind':'retry_confirmed_429','case_id':case,'arm':cfg['arm'],'ordinal':n,'predecessor_generation_id':x['id'],'predecessor_count_id':x['count_id'],'predecessor_db_sha256':snapshot['db_sha256'],'request_sha256':x['request_sha256'],'predecessor_response_sha256':x['response_sha256'],'count_response_sha256':x['count_response_sha256']}
   retried=True
  else:
   if not retried or n>23:raise Error('unattempted operation before failed recovery or arm cap')
   binding={'kind':'unattempted','case_id':case,'arm':cfg['arm'],'ordinal':n,'request_sha256':sha(raw)}
  if not callable(verify_live) or verify_live(copy.deepcopy(binding),copy.deepcopy(request)) is not True:raise Error('unverified live binding')
  response=generate(copy.deepcopy(binding),stage,copy.deepcopy(request))
  if not isinstance(response,bytes):raise Error('callback must return saved raw provider response bytes')
  return forecast.parse_response(json.loads(response))
 return run

def verify_replay(case):
 """Replay saved successes to exact historical 429, without model calls."""
 s=inspect(case);cb=_replayer(s)
 engine=forecast.BaselineEngine(cb,matched_calls=s['prior_c']['calls']) if s['prior_c'] else forecast.FaithfulEngine(cb)
 try:engine.run(copy.deepcopy(s['task']))
 except Reached429 as e:
  return {'case_id':case,'status':'exact_429_reconstructed','successful_replayed':CONFIG[case]['failed']-1,'failed_stage':str(e),'failed_request_sha256':s['records'][-1]['request_sha256']}
 raise Error('failed call was not reached')

def run_case(case,*,generate,verify_live,record,clock):
 """Explicit injected executor; this module cannot dispatch on its own.

 generate must use a successor journal, validate/consume inherited count for
 retries and perform new count+generation for previously untouched steps.
 Each returned response must be already persisted and charged before return.
 record must be exclusive, durable and receipt-bound; clock returns actual UTC.
 Stop on a further error without reattempting or claiming a complete pair.
 """
 if not all(callable(x) for x in (generate,verify_live,record,clock)):raise Error('missing reviewed callbacks')
 def deadline_now():
  value=clock()
  t=datetime.fromisoformat(value.replace('Z','+00:00'))
  if t.utcoffset() is None or t.utcoffset().total_seconds()!=0 or t>=DEADLINE:raise Error('original p0 deadline elapsed')
  return value
 def guarded(binding,request):
  deadline_now()
  return verify_live(binding,request)
 deadline_now()
 s=inspect(case);verify_replay(case)
 record(case+'-input',{'case_id':case,'task':copy.deepcopy(s['task']),'case':copy.deepcopy(s['case']),'historical_db_sha256':s['db_sha256'],'recovered_at_utc':deadline_now()})
 cb=_replayer(s,generate=generate,verify_live=guarded)
 if s['prior_c']:
  c=copy.deepcopy(s['prior_c']);b=forecast.BaselineEngine(cb,matched_calls=c['calls']).run(copy.deepcopy(s['task']))
  record(case+'-b',copy.deepcopy(b))
 else:
  c=forecast.FaithfulEngine(cb).run(copy.deepcopy(s['task']))
  record(case+'-c',copy.deepcopy(c));n=c.get('calls')
  if type(n) is not int or not 1<=n<=23:raise Error('invalid C call count')
  ordinal=0
  def fresh(stage,payload):
   nonlocal ordinal
   ordinal+=1
   if ordinal>n:raise Error('B count cap')
   request=forecast.build_request(stage,payload)
   binding={'kind':'unattempted','case_id':case,'arm':'b','ordinal':ordinal,'request_sha256':sha(canonical(request))}
   if guarded(copy.deepcopy(binding),copy.deepcopy(request)) is not True:raise Error('unverified B binding')
   raw=generate(copy.deepcopy(binding),stage,copy.deepcopy(request))
   if not isinstance(raw,bytes):raise Error('callback must return bytes')
   return forecast.parse_response(json.loads(raw))
  b=forecast.BaselineEngine(fresh,matched_calls=n).run(copy.deepcopy(s['task']))
  record(case+'-b',copy.deepcopy(b))
 completed=deadline_now()
 t=datetime.fromisoformat(completed.replace('Z','+00:00'))
 if t.utcoffset() is None or t.utcoffset().total_seconds()!=0:raise Error('completion must be UTC')
 out={'schema':'resumed-original-p0-v1','case_id':case,'as_of_utc':s['task']['as_of_utc'],'completed_at_utc':completed,'c':copy.deepcopy(c),'b':copy.deepcopy(b),'historical_db_sha256':s['db_sha256'],'comparison_eligible':c.get('status')=='proposal' and b.get('status')=='proposal','qualification':'as_of is input cutoff; completion time is actual, p1 requires news after durable receipt'}
 record(case+'-p0-frozen',copy.deepcopy(out))
 durable=deadline_now();td=datetime.fromisoformat(durable.replace('Z','+00:00'))
 if td.utcoffset() is None or td.utcoffset().total_seconds()!=0 or td<t:raise Error('invalid durable timestamp')
 receipt={'schema':'resumed-original-p0-receipt-v1','case_id':case,'frozen_sha256':sha(canonical(out)),'completed_at_utc':completed,'durable_before_utc':durable,'input_as_of_utc':s['task']['as_of_utc'],'comparison_eligible':out['comparison_eligible']}
 record(case+'-p0-receipt',copy.deepcopy(receipt));return receipt
