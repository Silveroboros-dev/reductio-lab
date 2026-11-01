"""Provider-free P1 input gate for the completed resumed CPI P0 pair.

No schema renaming, live calls, credentials, ledger writes or authority here.
The user, venue, source, and semantic verifiers remain independent duties.
Raw price/status fields are never projected into P1 task inputs.
"""
from __future__ import annotations
import copy,hashlib,json,sqlite3,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for folder in ('forecast-controller-v1','forecast-orchestrator-v1'):
 sys.path.insert(0,str(ROOT/folder))
import forecast,orchestrator as o

HASHES={
 'forecast-p0-429-resume-results-20261029-01/case-02-input.json':'8c67563dddc6b27c5ec47e97b6823d2194244fe36bd62134644d0fb47dcb8339',
 'forecast-p0-429-resume-results-20261029-01/case-02-p0-frozen.json':'17285df9ffacdfe999fd420a4493b7d9e25c1ae585c4783ba7930e5be4e9f065',
 'forecast-p0-429-resume-results-20261029-01/case-02-p0-receipt.json':'d4d0c8c75d4ba5c5168f9081ea96e30befbe9e08bc1b2329aafa7e524ad6e453',
 'forecast-p0-429-resume-results-20261029-01/case-02-b.json':'45e878b24c5792ab533e2362d58cf55b64a9c1d9a02bea47b3c3cbd415f77608',
 'forecast-p0-429-resume-results-20261029-01/summary.json':'7a0478f313c0aaf71fc4bfe13b33e5d525b43c05526455901e40d82d686d8ac1',
 'forecast-p0-429-resume-ledger-20261029-01/ledger.sqlite3':'43896046c4f9fa56e1bf85ff0afc47e6d5413d79047795761d6150125bfee3ba',
 'forecast-p0-remaining-results-20261029-01/00-p0-c.json':'e8f37e1eeb1d559feead828ad31a904ba9c5cfda9ca9786e3e9527f3f4e3b1e3',
 'forecast-p0-remaining-results-20261029-01/00-p0-input.json':'849dd5b06474ab90a200b0d2282f4b788e452f44f5a0857783b9fe1ee9647575',
 'forecast-429-recovery-ledger-20261029-01/ledger.sqlite3':'ee8670dbc34721e39aecaf4b8fe160e38e56af53a772872b323bcef05739a02b',
 'forecast-controller-v1/forecast.py':'596ee6fdc840977a4697536b0307585e79cadfcfb0b962225c0feb06a7e79b2f',
 'kalshi-user-message-transcription-correction-20261029-v1.json':'7eec8594f425405d3c8a9a164036e34efdc96dc90d656e066cc6ea27a7fab871',
 'kalshi-original-user-message-json-20261029-v1.raw.json':'93e201de87ee68504baafdafbf88ff8730e9d01e5cbf26359e49e93752768d37',
 'kalshi-user-relay-20261029-v1.raw.json':'459f460e7da6d6fcd81d837652f0a487cbe70e7d317f7a29907b5f0eb877bdf1',
}
DURABLE='2026-10-29T11:51:50.322164+00:00'
TICKER='KXCPI-26OCT-T0.2'
class Error(ValueError):pass

def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def _read(name):
 p=ROOT/name
 if name not in HASHES or not p.is_file() or p.is_symlink() or p.resolve()!=p.absolute():raise Error('unsafe or unbound p0 input')
 raw=p.read_bytes()
 if sha(raw)!=HASHES[name]:raise Error('p0 input drift: '+name)
 return raw

def _obj(raw):
 def pairs(xs):
  d={}
  for k,v in xs:
   if k in d:raise Error('duplicate JSON key')
   d[k]=v
  return d
 try:x=json.loads(raw,object_pairs_hook=pairs)
 except (ValueError,TypeError,UnicodeDecodeError):raise Error('invalid JSON') from None
 if not isinstance(x,dict):raise Error('object required')
 return x

def _db(name):
 _read(name)
 return sqlite3.connect('file:'+str(ROOT/name)+'?mode=ro&immutable=1',uri=True)

def verify_p0():
 """Validate exact saved CPI inputs, receipts, cost journal and local replay."""
 for name in HASHES:_read(name)
 oldprep=_obj(_read('forecast-p0-remaining-results-20261029-01/00-p0-input.json'))
 resumed=_obj(_read('forecast-p0-429-resume-results-20261029-01/case-02-input.json'))
 f=_obj(_read('forecast-p0-429-resume-results-20261029-01/case-02-p0-frozen.json'))
 receipt=_obj(_read('forecast-p0-429-resume-results-20261029-01/case-02-p0-receipt.json'))
 oldc=_obj(_read('forecast-p0-remaining-results-20261029-01/00-p0-c.json'))
 b=_obj(_read('forecast-p0-429-resume-results-20261029-01/case-02-b.json'))
 summary=_obj(_read('forecast-p0-429-resume-results-20261029-01/summary.json'))
 correction=_obj(_read('kalshi-user-message-transcription-correction-20261029-v1.json'))
 original=_obj(_read('kalshi-original-user-message-json-20261029-v1.raw.json'))
 copied=_obj(_read('kalshi-user-relay-20261029-v1.raw.json'))
 if (correction.get('schema')!='user-relay-manual-transcription-correction-v1' or correction.get('origin',{}).get('kind')!='original_user_question_reply_in_task_history' or
  correction.get('original_message_json',{}).get('sha256')!=HASHES['kalshi-original-user-message-json-20261029-v1.raw.json'] or
  correction.get('prior_copy',{}).get('sha256')!=HASHES['kalshi-user-relay-20261029-v1.raw.json'] or
  correction.get('transcription_error',{}).get('path')!='$.markets[3].occurrence_datetime'):
  raise Error('user-message correction mismatch')
 try:
  if 'occurrence_datetime' in original['markets'][3] or copied['markets'][3].pop('occurrence_datetime')!='2026-10-09T04:30:00Z' or original!=copied:raise Error('unexpected relay difference')
  market=original['markets'][3]
 except (KeyError,IndexError,TypeError):raise Error('invalid corrected market evidence') from None
 if (resumed.get('case_id')!='case-02' or resumed.get('case')!=oldprep.get('case') or resumed.get('task')!=oldprep.get('task') or
  oldprep['case'].get('contract_id')!=TICKER or sha(canonical(oldprep['case']))!=oldprep.get('case_sha256') or sha(canonical(oldprep['task']))!=oldprep.get('task_sha256')):raise Error('case or task binding mismatch')
 if (market.get('ticker')!=TICKER or market.get('rules_primary')!=oldprep['case']['rules_primary'] or
  market.get('rules_secondary')!=oldprep['case']['rules_secondary'] or market.get('close_time')!=oldprep['case']['close_time_utc'] or
  market.get('status')!='active' or market.get('result')!='' or (market.get('yes_bid_dollars'),market.get('yes_ask_dollars'))!=('0.5600','0.5800')):
  raise Error('CPI projected rules/status/quote mismatch to original user message')
 quotes=[e for e in oldprep['task']['evidence'] if e.get('id')=='market:quote']
 if len(quotes)!=1 or quotes[0].get('text')!='User-relayed market snapshot reports YES bid 0.5600 USD and YES ask 0.5800 USD; quote may be stale.':raise Error('CPI p0 quote differs')
 if (f.get('schema')!='resumed-original-p0-v1' or receipt.get('schema')!='resumed-original-p0-receipt-v1' or
  f.get('case_id')!='case-02' or receipt.get('case_id')!='case-02' or f.get('c')!=oldc or f.get('b')!=b or
  f.get('comparison_eligible') is not True or receipt.get('comparison_eligible') is not True or
  receipt.get('frozen_sha256')!=sha(canonical(f)) or receipt.get('input_as_of_utc')!=oldprep['task']['as_of_utc'] or
  f.get('as_of_utc')!=oldprep['task']['as_of_utc'] or receipt.get('completed_at_utc')!=f.get('completed_at_utc') or
  receipt.get('durable_before_utc')!=DURABLE or o.instant(f['completed_at_utc'])>o.instant(DURABLE)):
  raise Error('resumed receipt or p0 lineage mismatch')
 if summary.get('status')!='completed_p0_only' or sum(x==receipt for x in summary.get('outcomes',[]))!=1:raise Error('p0 receipt missing from completed batch')
 if any(f.get(arm,{}).get('status')!='proposal' or f[arm].get('calls')!=8 for arm in ('c','b')):raise Error('complete matched C/B p0 required')
 old=_db('forecast-429-recovery-ledger-20261029-01/ledger.sqlite3')
 new=_db('forecast-p0-429-resume-ledger-20261029-01/ledger.sqlite3')
 try:
  state=new.execute('SELECT stopped,exposure_micro,generation_attempts,count_attempts,source_attempts FROM run').fetchone()
  if state!=(0,1988563,299,228,0) or summary.get('ledger',{}).get('source_attempts')!=16:raise Error('resume ledger state mismatch')
  if new.execute("SELECT count(*) FROM effects WHERE state!='succeeded' OR http_status!=200 OR actual_micro IS NULL").fetchone()!=(0,):raise Error('unsettled resumed effects')
  def replay(arm):
   n=0
   def gen(stage,payload):
    nonlocal n
    n+=1;logical=f'p0:case-02:{arm}:{n:02d}'
    if arm=='c' or n<=4:db=old;ident='generation:'+logical
    else:db=new;ident=('retry1:generation:'+logical if n==5 else 'newgeneration:'+logical)
    row=db.execute('SELECT request,request_hash,response,response_hash,state,http_status,actual_micro,related_id FROM effects WHERE id=? AND kind="generation"',(ident,)).fetchone()
    if row is None:raise Error('p0 generation missing '+ident)
    req,rh,resp,sh,state,status,actual,related=row;expected=canonical(forecast.build_request(stage,payload))
    if (bytes(req)!=expected or sha(bytes(req))!=rh or sha(bytes(resp))!=sh or state!='succeeded' or status!=200 or actual is None):raise Error('p0 generation receipt mismatch')
    if arm=='b' and n==5:
     oldcount=old.execute('SELECT request_hash,response_hash,http_status,actual_micro FROM effects WHERE id=?',('count:'+logical,)).fetchone()
     if oldcount is None or oldcount[0]!=rh or oldcount[2:]!=(200,0) or related!='historical-count:'+HASHES['forecast-429-recovery-ledger-20261029-01/ledger.sqlite3']+':count:'+logical+':'+oldcount[1]:raise Error('inherited count mismatch')
    if arm=='b' and n>5 and related!='newcount:'+logical:raise Error('new count binding mismatch')
    return forecast.parse_response(json.loads(resp))
   engine=forecast.FaithfulEngine(gen) if arm=='c' else forecast.BaselineEngine(gen,matched_calls=8)
   result=engine.run(copy.deepcopy(oldprep['task']))
   if result!=f[arm] or n!=8:raise Error('offline model trace reconstruction mismatch')
  replay('c');replay('b')
 finally:old.close();new.close()
 return {'prepared':oldprep,'p0_frozen':f,'receipt':receipt,
  'p0_receipt_sha256':HASHES['forecast-p0-429-resume-results-20261029-01/case-02-p0-receipt.json'],
  'p0_ledger_sha256':HASHES['forecast-p0-429-resume-ledger-20261029-01/ledger.sqlite3'],
  'source_correction_sha256':HASHES['kalshi-user-message-transcription-correction-20261029-v1.json'],
  'qualification':'Previous source hash identifies our copy with an added occurrence field, not exact user text or direct network bytes; actual p0 rules/quote match the original user message. Source transport independently unverified.'}

def pending(reason):return {'status':'pending','reason':reason}

def prepare(news,status,*,t1,verify_news,verify_status,max_status_age_seconds=300):
 """Prepare four P1 arms, or pending; source/status verifiers required.

 News verification must establish source authenticity, actual first-publication
 time, exact new content and semantic relevance. Status verification must bind
 same full rules and unresolved status to an attributable fresh snapshot.
 No verifier callback defaults are provided; their claims are not human review.
 """
 if not news:return pending('no_eligible_new_event')
 if status is None:return pending('unresolved_market_not_verified')
 if not callable(verify_news) or not callable(verify_status):raise Error('independent source and status verifiers required')
 if type(max_status_age_seconds) is not int or not 0<max_status_age_seconds<=300:raise Error('invalid status freshness')
 checked=verify_p0();prepared=checked['prepared'];f=checked['p0_frozen'];case=prepared['case'];task=prepared['task']
 try:t=o.instant(t1);durable=o.instant(DURABLE);close=o.instant(case['close_time_utc'])
 except (o.EligibilityError,KeyError):return pending('invalid_t1_or_case_time')
 if not durable<t<close:return pending('t1_outside_open_interval')
 if not isinstance(news,list) or not news:return pending('news_not_list')
 baseids={e['id'] for e in task['evidence']};basetexts={e['text'].strip() for e in task['evidence']};newsids=set()
 for e in news:
  if not isinstance(e,dict) or e.get('kind')!='news' or not isinstance(e.get('id'),str) or e['id'] in baseids or e['id'] in newsids or not isinstance(e.get('text'),str) or not e['text'].strip() or e['text'].strip() in basetexts:return pending('news_duplicate_or_invalid')
  newsids.add(e['id'])
  try:pub=o.instant(e.get('published_at_utc'));avail=o.instant(e.get('available_at_utc'));captured=o.instant(e.get('captured_at_utc'))
  except o.EligibilityError:return pending('news_timestamp_missing')
  if not durable<pub<=avail<=captured<=t:return pending('news_not_provably_after_durable_p0')
 if verify_news(copy.deepcopy(news),t1) is not True:return pending('news_provenance_or_semantic_novelty_unconfirmed')
 if not isinstance(status,dict) or status.get('contract_id')!=TICKER or status.get('state')!='active' or status.get('result')!='' or status.get('rules_primary')!=case['rules_primary'] or status.get('rules_secondary')!=case['rules_secondary']:return pending('market_not_verified_open_with_same_rules')
 try:obs=o.instant(status.get('observed_at_utc'));capt=o.instant(status.get('captured_at_utc'))
 except o.EligibilityError:return pending('status_timestamp_missing')
 if not (max(o.instant(e['captured_at_utc']) for e in news)<=obs<=capt<=t) or (t-capt).total_seconds()>max_status_age_seconds:return pending('market_status_stale_or_before_news')
 if verify_status(copy.deepcopy(status),copy.deepcopy(case),t1) is not True:return pending('market_unresolved_unconfirmed')
 tasks={}
 for arm in ('c','b'):
  for condition in ('no_news','news'):
   new=copy.deepcopy(task);new.update(phase='p1',condition=condition,as_of_utc=t1,prior_forecast=copy.deepcopy(f[arm]['result']))
   if condition=='news':new['evidence']+=copy.deepcopy(news)
   forecast.prepare_task(new);tasks[arm+'_'+condition]=new
 bundle={'schema':'forecast-p1-input-v1','case_sha256':oldprep_sha(prepared),'p0_sha256':checked['p0_receipt_sha256'],
  'intervention_sha256':sha(canonical(news)),'t1':t1,'tasks':tasks}
 return {'status':'ready','bundle':bundle,'bundle_sha256':sha(canonical(bundle)),'status_evidence_sha256':sha(canonical(status)),
  'status_observed_at_utc':status['observed_at_utc'],'status_captured_at_utc':status['captured_at_utc'],
  'max_status_age_seconds':max_status_age_seconds,'p0_receipt_schema':'resumed-original-p0-receipt-v1',
  'p0_receipt_sha256':checked['p0_receipt_sha256'],'p0_ledger_sha256':checked['p0_ledger_sha256'],
  'source_correction_sha256':checked['source_correction_sha256'],
  'limitation':'Current venue status is an observation, not a guarantee against subsequent early resolution.'}

def oldprep_sha(prepared):
 value=prepared.get('case_sha256')
 if value!=sha(canonical(prepared.get('case'))):raise Error('case SHA mismatch')
 return value
