"""Receipt-bound market observations across original and recovery ledgers.

Only local gateway-receipt time is verified. Upstream cache age is unknown.
"""
import copy,json,sqlite3
from pathlib import Path
import gate,conditional_capture,venue_capture
class Error(ValueError):pass

def verify_status(status,case,at,*,recovery_db):
 try:
  ident=status['source_op_id']
  if ident=='p1-cpi-status-03':return venue_capture.verify_status(status,case,at)
  if ident not in [f'p1-cpi-status-{n:02d}' for n in range(4,9)]:return False
  if gate.sha(conditional_capture.CONTRACT.read_bytes())!=conditional_capture.SOURCE_CONTRACT_SHA:return False
  contract=json.loads(conditional_capture.CONTRACT.read_bytes());ops=[x for x in contract['operations'] if x['kind']=='status_refresh' and x['ticket']['id']==ident]
  if len(ops)!=1:return False
  op=ops[0];db=sqlite3.connect('file:'+str(recovery_db)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
  try:row=db.execute('select * from effects where id=?',(ident,)).fetchone()
  finally:db.close()
  if row is None:return False
  row=dict(row);raw=bytes(row['response']);req=gate.canonical(op['payload'])
  if (row['kind'],row['provider'],row['endpoint'],row['state'],row['http_status'])!=('source','orthogonal','/v1/run','succeeded',200):return False
  if bytes(row['request'])!=req or row['request_hash']!=gate.sha(req) or row['response_hash']!=status['response_sha256'] or gate.sha(raw)!=row['response_hash'] or row['actual_micro'] is None:return False
  decoded=venue_capture.extract(raw)
  if any(status.get(k)!=val for k,val in decoded.items()) or status['observed_at_utc']!=row['completed_at_utc'] or status['captured_at_utc']!=row['completed_at_utc']:return False
  if status['state']!='active' or status['result']!='' or status['rules_primary']!=case['rules_primary'] or status['rules_secondary']!=case['rules_secondary']:return False
  obs=gate.o.instant(status['captured_at_utc']);now=gate.o.instant(at);return obs<=now and 0<=(now-obs).total_seconds()<=300
 except (OSError,KeyError,ValueError,TypeError,sqlite3.Error,gate.o.EligibilityError):return False

def make_refresher(stage,operations,*,transport,verify_ticket,record):
 if not isinstance(operations,list) or [o['ticket']['id'] for o in operations]!=[f'p1-cpi-status-{n:02d}' for n in range(4,9)]:raise Error('exact remaining status operations required')
 cursor=0
 def refresh():
  nonlocal cursor
  if cursor>=len(operations):raise Error('remaining status observations exhausted')
  op=copy.deepcopy(operations[cursor]);cursor+=1;ident=op['ticket']['id'];raw=stage.status_source(ident,transport,verify_ticket);r=stage.receipt(ident)
  if (r.get('id'),r.get('kind'),r.get('state'),r.get('http_status'))!=(ident,'source','succeeded',200) or r.get('request_hash')!=gate.sha(gate.canonical(op['payload'])) or r.get('response_hash')!=gate.sha(raw) or bytes(r.get('response',b''))!=raw or type(r.get('actual_micro')) is not int:raise Error('status receipt invalid')
  status=venue_capture.extract(raw);status.update(source_op_id=ident,response_sha256=r['response_hash'],observed_at_utc=r['completed_at_utc'],captured_at_utc=r['completed_at_utc'])
  record('source-'+ident,{'id':ident,'request_sha256':r['request_hash'],'response_sha256':r['response_hash'],'started_at_utc':r['started_at_utc'],'completed_at_utc':r['completed_at_utc'],'actual_micro':r['actual_micro']})
  return status
 return refresh
