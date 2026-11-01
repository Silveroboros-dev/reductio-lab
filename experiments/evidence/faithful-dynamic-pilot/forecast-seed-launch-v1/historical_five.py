"""Read-only verification of the settled source stage, never dispatch.

Historical quotes are validated at their actual started_at_utc, not against the
current clock. A valid historical quote does not authorize a new source call.
"""
import datetime as dt, fcntl, hashlib, json, os, sqlite3
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
SOURCE_SHA='009a8d5e401213a93c2183ef48c616383c84413d6ea668cb445c3aaf7c3d0e38'
YOU_SHA='21d02f21d43892bf99d7be1f0b46b613c31a407f56722e6b82a4e834ed0ffbbc'
class Error(ValueError):pass
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def read(p):
 p=Path(p)
 if not p.is_absolute() or p.is_symlink() or not p.is_file() or p.resolve()!=p.absolute():raise Error('unsafe historical path')
 return p.read_bytes()
def obj(raw):
 def pairs(xs):
  d={}
  for k,v in xs:
   if k in d:raise Error('duplicate JSON key')
   d[k]=v
  return d
 try:r=json.loads(raw,object_pairs_hook=pairs)
 except (ValueError,UnicodeDecodeError,TypeError):raise Error('invalid JSON') from None
 if not isinstance(r,dict):raise Error('expected object')
 return r
def utc(s):
 try:t=dt.datetime.fromisoformat(s.replace('Z','+00:00'))
 except (ValueError,AttributeError):raise Error('invalid UTC timestamp') from None
 if t.utcoffset()!=dt.timedelta(0):raise Error('non-UTC timestamp')
 return t

def you_evidence():
 ar=read(ROOT/'forecast-source-you-addendum-20261029-v1.json')
 pr=read(ROOT/'forecast-you-challenge-packet-v1.json');rr=read(ROOT/'forecast-you-challenge-receipt-v1.json')
 a,p,r=map(obj,(ar,pr,rr));d=p.get('internal_digest');w=p.get('context_binding',{})
 if (sha(ar)!=YOU_SHA or a.get('schema')!='faithful-forecast-source-addendum-v1' or a.get('status')!='frozen'
  or a.get('parent_contract_sha256')!=SOURCE_SHA or p.get('schema_version')!='eval_contract_challenge_packet_v1'
  or p.get('overall_state')!='ready' or p.get('witness',{}).get('identity')!='you_source_witness'
  or p.get('witness',{}).get('mode')!='read_only_offline' or p.get('challenged_contract',{}).get('raw_sha256')!=YOU_SHA
  or d!=sha(canonical({k:v for k,v in p.items() if k!='internal_digest'})) or r.get('packet_raw_sha256')!=sha(pr)
  or r.get('packet_byte_count')!=len(pr) or r.get('packet_internal_digest')!=d or r.get('state')!='ready'):
  raise Error('You addendum or independent challenge mismatch')
 if any(w.get(k)!=a.get(k) for k in ('execution_context','operation','source_parent')):raise Error('You challenge scope mismatch')
 inspected=w.get('code_bindings_at_inspection',{})
 for rel,h in a.get('component_bindings',{}).items():
  raw=read(ROOT/rel)
  if sha(raw)!=h or inspected.get(rel)!={'sha256':h,'size':len(raw)}:raise Error('You component mismatch')
 out=Path(a['execution_context']['output_root'])
 if out!=ROOT/'forecast-source-you-20261029-01':raise Error('You output context mismatch')
 started=obj(read(out/'started.json'));summary_raw=read(out/'summary.json');summary=obj(summary_raw)
 if (started.get('addendum_sha256')!=YOU_SHA or started.get('challenge_sha256')!=sha(pr) or
  started.get('receipt_sha256')!=sha(rr) or started.get('operation_id')!='seed-openai-you-search' or
  summary.get('status')!='completed' or summary.get('failure') is not None):raise Error('You stage did not settle')
 quote_raw=read(ROOT/'forecast-you-price-20261029.json');quote=obj(quote_raw)
 if sha(quote_raw)!=a['operation']['ticket']['evidence_sha256'] or quote.get('rate_usd')!='0.005 per call':raise Error('You quote mismatch')
 return a,p,r,summary,summary_raw,quote

def verify(*,require_seed_start_state=True):
 """Verify bytes, challenge, source price timing, four settled effects offline."""
 contract_raw=read(ROOT/'forecast-source-run-contract-20261029-v1.json')
 packet_raw=read(ROOT/'forecast-source-challenge-packet-v1.json')
 receipt_raw=read(ROOT/'forecast-source-challenge-receipt-v1.json')
 c,p,r=map(obj,(contract_raw,packet_raw,receipt_raw));d=p.get('internal_digest')
 if (sha(contract_raw)!=SOURCE_SHA or c.get('schema')!='faithful-forecast-run-contract-v1' or c.get('status')!='frozen'
  or p.get('schema_version')!='eval_contract_challenge_packet_v1' or p.get('overall_state')!='ready'
  or p.get('witness',{}).get('identity')!='source_witness' or p.get('witness',{}).get('mode')!='read_only_offline'
  or p.get('challenged_contract',{}).get('raw_sha256')!=SOURCE_SHA or d!=sha(canonical({k:v for k,v in p.items() if k!='internal_digest'}))
  or r.get('packet_raw_sha256')!=sha(packet_raw) or r.get('packet_byte_count')!=len(packet_raw) or r.get('packet_internal_digest')!=d or r.get('state')!='ready'):
  raise Error('historical source contract or independent challenge mismatch')
 w=p.get('context_binding',{});components=c.get('component_bindings',{})
 if w.get('execution_context')!=c.get('execution_context') or w.get('source_phase')!=c.get('source_phase'):
  raise Error('historical challenge context mismatch')
 inspected=w.get('code_bindings_at_inspection',{})
 for rel,digest in components.items():
  raw=read(ROOT/rel)
  if sha(raw)!=digest or inspected.get(rel)!={'sha256':digest,'size':len(raw)}:raise Error('historical code mismatch')
 a,yp,yr,ys,ysraw,yquote=you_evidence()
 ctx=c['execution_context'];out=Path(ctx['output_root']);ledger=Path(ctx['ledger_root'])
 if ctx.get('artifact_root')!=str(ROOT) or ctx.get('cwd')!=str(ROOT) or ledger!=ROOT/'forecast-live-ledger-20261029-01':
  raise Error('historical execution context mismatch')
 started_raw=read(out/'started.json');summary_raw=read(out/'summary.json');started,summary=map(obj,(started_raw,summary_raw))
 ops=c['source_phase']['requests'];ids=[x['id'] for x in ops]
 if (len(ops)!=4 or started.get('contract_sha256')!=SOURCE_SHA or started.get('challenge_sha256')!=sha(packet_raw)
  or started.get('receipt_sha256')!=sha(receipt_raw) or started.get('operation_ids')!=ids
  or summary.get('status')!='completed' or summary.get('failure') is not None or summary.get('not_attempted')!=0
  or [r.get('id') for r in summary.get('settled_records',[])]!=ids):raise Error('source phase did not fully settle')
 quote=obj(read(ROOT/'forecast-source-quotes-20261029.json'));observed=utc(quote['observed_at_utc'])
 if sha(read(ROOT/'forecast-source-quotes-20261029.json'))!=c['source_phase']['ui_sha256']:raise Error('source quote binding mismatch')
 if ledger.is_symlink() or not ledger.is_dir():raise Error('ledger missing')
 for suffix in ('-journal','-wal'):
  if (ledger/('ledger.sqlite3'+suffix)).exists():raise Error('unreconciled source journal')
 fd=os.open(ledger/'owner.lock',os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
 try:
  fcntl.flock(fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
  db_path=ledger/'ledger.sqlite3'
  if db_path.is_symlink() or not db_path.is_file():raise Error('source ledger missing')
  db=sqlite3.connect(db_path.as_uri()+'?mode=ro&immutable=1',uri=True)
  try:
   rows=db.execute("SELECT id,kind,provider,endpoint,request,request_hash,quote_micro,quote_evidence_sha,state,http_status,response,response_hash,actual_micro,quote_metadata,started_at_utc,completed_at_utc FROM effects WHERE kind='source' ORDER BY rowid").fetchall()
   if [x[0] for x in rows]!=ids+['seed-openai-you-search']:raise Error('source effect set drifted')
   for row,rec,settled in zip(rows[:4],ops,summary['settled_records']):
    (ident,kind,provider,endpoint,req,rhash,reserve,qsha,state,status,response,reshash,actual,meta,start,end)=row
    ticket=rec['ticket'];payload=canonical(rec['payload']);q=obj(meta)
    if (kind!='source' or provider!='orthogonal' or endpoint!='/v1/run' or req!=payload or rhash!=sha(payload)
     or q!=ticket or qsha!=c['source_phase']['ui_sha256'] or reserve!=ticket['max_micro']
     or state!='succeeded' or status!=200 or sha(response)!=reshash or type(actual) is not int
     or settled.get('state')!='succeeded' or settled.get('http_status')!=200
     or settled.get('response_sha256')!=reshash or settled.get('actual_micro')!=actual
     or settled.get('started_at_utc')!=start or settled.get('completed_at_utc')!=end):raise Error('source receipt mismatch')
    if not observed<=utc(start)<utc(ticket['expires_utc']) or utc(start)>utc(end):raise Error('source quote was not valid at effect start')
    response_obj=obj(response)
    if response_obj.get('success') is not True or response_obj.get('data') is None or Decimal(str(response_obj.get('priceCents')))*10000!=actual or actual>rec['ui_expected_micro']:
     raise Error('source price/response mismatch')
    if read(out/(ident+'.raw.json'))!=response:raise Error('captured raw source differs')
    ev=db.execute('SELECT state,detail FROM events WHERE effect_id=? ORDER BY seq',(ident,)).fetchall()
    if ev!=[('prepared',None),('started',None),('succeeded',None),('accounted',str(actual))]:raise Error('source effect state mismatch')
   row=rows[4]
   (ident,kind,provider,endpoint,req,rhash,reserve,qsha,state,status,response,reshash,actual,meta,start,end)=row
   rec=a['operation'];ticket=rec['ticket'];settled=ys.get('record',{});payload=canonical(rec['payload'])
   if (ident!=rec['id'] or kind!='source' or provider!='orthogonal' or endpoint!='/v1/run' or req!=payload or
    rhash!=sha(payload) or obj(meta)!=ticket or qsha!=ticket['evidence_sha256'] or reserve!=ticket['max_micro'] or
    state!='succeeded' or status!=200 or sha(response)!=reshash or type(actual) is not int or
    settled.get('id')!=ident or settled.get('state')!='succeeded' or settled.get('http_status')!=200 or
    settled.get('response_sha256')!=reshash or settled.get('actual_micro')!=actual or
    settled.get('started_at_utc')!=start or settled.get('completed_at_utc')!=end):raise Error('You receipt mismatch')
   if not utc(yquote['observed_at_utc'])<=utc(start)<utc(ticket['expires_utc']) or utc(start)>utc(end):
    raise Error('You quote was not valid at effect start')
   robj=obj(response)
   if robj.get('success') is not True or robj.get('data') is None or Decimal(str(robj.get('priceCents')))*10000!=actual or actual>rec['ui_expected_micro']:
    raise Error('You response or price mismatch')
   if read(ROOT/'forecast-source-you-20261029-01/seed-openai-you-search.raw.json')!=response:
    raise Error('You raw capture mismatch')
   ev=db.execute('SELECT state,detail FROM events WHERE effect_id=? ORDER BY seq',(ident,)).fetchall()
   if ev!=[('prepared',None),('started',None),('succeeded',None),('accounted',str(actual))]:raise Error('You effect state mismatch')
   current=db.execute('SELECT stopped,exposure_micro,generation_attempts,count_attempts,source_attempts FROM run WHERE id=1').fetchone()
   if require_seed_start_state and current!=(0,1234590+actual,200,132,5):raise Error('unexpected starting usage or earlier model run')
  finally:db.close()
 finally:
  fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
 parent={'source_contract_sha256':SOURCE_SHA,'source_challenge_sha256':sha(packet_raw),
  'source_receipt_sha256':sha(receipt_raw),'source_summary_sha256':sha(summary_raw),
  'source_ids':ids,'source_cost_micro':sum(r['actual_micro'] for r in summary['settled_records']),
  'original_quote_valid_at_each_start':True}
 if a.get('source_parent')!=parent:raise Error('You addendum not bound to original settled sources')
 return {'source_parent':parent,'you_addendum_sha256':YOU_SHA,
   'you_challenge_sha256':sha(read(ROOT/'forecast-you-challenge-packet-v1.json')),
   'you_receipt_sha256':sha(read(ROOT/'forecast-you-challenge-receipt-v1.json')),
   'you_summary_sha256':sha(ysraw),'you_source_id':'seed-openai-you-search',
   'you_cost_micro':ys['record']['actual_micro'],'you_quote_valid_at_start':True}
