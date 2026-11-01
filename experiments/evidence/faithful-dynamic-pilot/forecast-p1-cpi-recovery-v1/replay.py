"""Deterministically replay the captured P1 C no-news prefix, offline only.

The eighth generation received HTTP 200 but an unusable JSON body. This replay
never repairs that response, mutates its journal, or contacts any provider.
"""
import hashlib,json,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for d in ('forecast-p1-cpi-resumed-v1','forecast-controller-v1'):sys.path.insert(0,str(ROOT/d))
import gate,forecast,admission_evidence
DB=ROOT/'forecast-cpi-p1-retry-ledger-20261029-01/ledger.sqlite3'
class Error(ValueError):pass
class ReachedFormatter(Exception):pass

def sha(b):return hashlib.sha256(b).hexdigest()
def read_rows():
 d=sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True);d.row_factory=sqlite3.Row
 try:
  ids=[f'{kind}:p1:case-02:no_news:c:{i:02d}' for i in range(1,9) for kind in ('count','generation')]
  rows={i:dict(d.execute('select * from effects where id=?',(i,)).fetchone() or {}) for i in ids}
  other=d.execute("select id from effects where kind in ('count','generation') and id not like '%:p1:case-02:no_news:c:%' order by id").fetchall()
 finally:d.close()
 if other:raise Error('unexpected later model operations')
 for i in range(1,9):
  c=rows[f'count:p1:case-02:no_news:c:{i:02d}'];g=rows[f'generation:p1:case-02:no_news:c:{i:02d}']
  for x,k in ((c,'count'),(g,'generation')):
   if not x or x['kind']!=k or x['state']!='succeeded' or x['http_status']!=200 or x['actual_micro'] is None or sha(bytes(x['request']))!=x['request_hash'] or sha(bytes(x['response']))!=x['response_hash']:raise Error('missing or unverified prior receipt')
  if c['request']!=g['request'] or g['related_id']!=c['id']:raise Error('generation and original count not matched')
 return rows

def proof():
 pre=admission_evidence.inspect();task=pre['admission']['bundle']['tasks']['c_no_news'];rows=read_rows();ordinal=0;stages=[]
 def replay(stage,payload):
  nonlocal ordinal
  ordinal+=1;ident=f'p1:case-02:no_news:c:{ordinal:02d}';c=rows['count:'+ident];g=rows['generation:'+ident]
  raw=gate.canonical(forecast.build_request(stage,payload));stages.append(stage)
  if bytes(g['request'])!=raw or bytes(c['request'])!=raw:raise Error(f'original request mismatch {ordinal}')
  if ordinal==8:
   if stage!='formatter':raise Error('failure not at expected formatter')
   try:forecast.parse_response(json.loads(g['response']))
   except ValueError:raise ReachedFormatter from None
   raise Error('formatter unexpectedly parses')
  return forecast.parse_response(json.loads(g['response']))
 engine=forecast.FaithfulEngine(replay,max_calls=23)
 try:engine.run(task)
 except ReachedFormatter:pass
 else:raise Error('failed formatter not reached')
 if ordinal!=8:raise Error('unexpected replay count')
 g=rows['generation:p1:case-02:no_news:c:08'];c=rows['count:p1:case-02:no_news:c:08'];body=json.loads(g['response']);text=body['candidates'][0]['content']['parts'][0]['text']
 try:json.loads(text)
 except json.JSONDecodeError as e:failure={'type':'invalid_json','message':e.msg,'character':e.pos,'line':e.lineno,'column':e.colno,'bad_excerpt':text[max(0,e.pos-22):e.pos+30]}
 else:raise Error('no JSON error')
 return {'schema':'cpi-p1-invalid-formatter-replay-proof-v1','case_id':'case-02','phase':'p1','condition':'no_news','arm':'c',
  'admission_sha256':gate.sha(gate.canonical(pre['admission'])),'successful_prefix_generations':7,'successful_prefix_count_tokens':8,
  'stages':stages,'failed_id':g['id'],'failed_request_sha256':g['request_hash'],'failed_response_sha256':g['response_hash'],
  'failed_actual_micro':g['actual_micro'],'reusable_count_id':c['id'],'reusable_count_response_sha256':c['response_hash'],
  'failed_http_status':g['http_status'],'failure':failure,'actual_first_response_preserved':True,
  'qualification':'Replay is deterministic; subsequent identical model request would be a newly charged physical attempt, never a repeat of a valid prior result. B matching uses logical successful C calls; physical retry remains disclosed.'}

def repaired_outcome():
 """Apply one declared literal quote insertion to the known malformed text.

 The original response remains untouched. Validate via the original engine;
 this post-hoc outcome must never be described as strict protocol compliant.
 """
 checked=proof();pre=admission_evidence.inspect();task=pre['admission']['bundle']['tasks']['c_no_news'];rows=read_rows();ordinal=0;repair_record={}
 def generate(stage,payload):
  nonlocal ordinal
  ordinal+=1;ident=f'p1:case-02:no_news:c:{ordinal:02d}';g=rows['generation:'+ident];c=rows['count:'+ident];raw=gate.canonical(forecast.build_request(stage,payload))
  if raw!=bytes(g['request']) or raw!=bytes(c['request']):raise Error('request mismatch on repaired replay')
  original=json.loads(g['response'])
  if ordinal!=8:return forecast.parse_response(original)
  if stage!='formatter' or g['request_hash']!=checked['failed_request_sha256'] or g['response_hash']!=checked['failed_response_sha256']:raise Error('wrong repair target')
  parts=original['candidates'][0]['content']['parts'];text=parts[0]['text'];position=checked['failure']['character']
  if not text[position:].startswith('citations"'):raise Error('precise quote-insertion site not found')
  fixed=text[:position]+'"'+text[position:]
  if fixed[:position]+fixed[position+1:]!=text:raise Error('repair differs beyond one character')
  parts[0]['text']=fixed
  result=forecast.parse_response(original)
  repair_record.update({'method':'single character insertion, double quote before citations key','character_position':position,
   'original_text_sha256':sha(text.encode()),'derived_text_sha256':sha(fixed.encode()),'derived_text':fixed,'original_raw_response_sha256':g['response_hash'],
   'original_http_status':200,'original_strict_parse':'invalid JSON','posthoc_repair':True})
  return result
 engine=forecast.FaithfulEngine(generate,max_calls=23);outcome=engine.run(task)
 if ordinal!=8 or outcome.get('status')!='proposal' or outcome.get('calls')!=8:raise Error('repair did not yield a validated proposal')
 return {'schema':'cpi-p1-posthoc-format-repair-v1','proof':checked,'repair':repair_record,'outcome':outcome,
  'qualification':'Only a deterministic one-character formatting repair; original response failed strict JSON parsing. This is a post-hoc exploratory result, not a valid strict-protocol output.'}
