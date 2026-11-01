"""Status verification for stopped predecessor 05 and successor 06–18.

Gateway receipt time is local; upstream cache age is not established.
"""
import copy,sqlite3
from pathlib import Path
import gate,venue_capture,reconstruct
class Error(ValueError):pass

def verify_status(status,case,at,*,successor_db,operations):
 try:
  ident=status['source_op_id'];dbpath=reconstruct.PARENT if ident=='p1-cpi-status-05' else Path(successor_db)
  if ident!='p1-cpi-status-05' and ident not in [f'p1-cpi-status-{i:02d}' for i in range(6,19)]:return False
  ops=[x for x in operations if x.get('ticket',{}).get('id')==ident] if ident!='p1-cpi-status-05' else []
  db=sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
  try:row=db.execute('select * from effects where id=?',(ident,)).fetchone()
  finally:db.close()
  if row is None:return False
  row=dict(row);raw=bytes(row['response'])
  if (row['kind'],row['provider'],row['endpoint'],row['state'],row['http_status'])!=('source','orthogonal','/v1/run','succeeded',200):return False
  if ident=='p1-cpi-status-05':
   if row['response_hash']!='0f8cff07c0f2288c7df936fc5101c15e324572ab816a9c738195c09aad8c8633':return False
  else:
   if len(ops)!=1 or bytes(row['request'])!=gate.canonical(ops[0]['payload']) or row['request_hash']!=gate.sha(bytes(row['request'])):return False
  if row['response_hash']!=status['response_sha256'] or gate.sha(raw)!=row['response_hash'] or type(row['actual_micro']) is not int:return False
  decoded=venue_capture.extract(raw)
  if any(status.get(k)!=val for k,val in decoded.items()) or status['observed_at_utc']!=row['completed_at_utc'] or status['captured_at_utc']!=row['completed_at_utc']:return False
  if status['state']!='active' or status['result']!='' or status['rules_primary']!=case['rules_primary'] or status['rules_secondary']!=case['rules_secondary']:return False
  observed=gate.o.instant(status['captured_at_utc']);current=gate.o.instant(at);return observed<=current and 0<=(current-observed).total_seconds()<=300
 except (OSError,KeyError,ValueError,TypeError,sqlite3.Error,gate.o.EligibilityError):return False

def refresher(stage,operations,*,transport,verify_ticket,record):
 if [x.get('ticket',{}).get('id') for x in operations]!=[f'p1-cpi-status-{i:02d}' for i in range(6,19)]:raise Error('unexpected status operations')
 cursor=0
 def call():
  nonlocal cursor
  if cursor>=len(operations):raise Error('status operation limit exhausted')
  op=copy.deepcopy(operations[cursor]);cursor+=1;ident=op['ticket']['id'];raw=stage.status_source(ident,transport,verify_ticket);r=stage.receipt(ident)
  if (r.get('id'),r.get('kind'),r.get('state'),r.get('http_status'))!=(ident,'source','succeeded',200) or r.get('request_hash')!=gate.sha(gate.canonical(op['payload'])) or r.get('response_hash')!=gate.sha(raw) or bytes(r.get('response',b''))!=raw or type(r.get('actual_micro')) is not int:raise Error('status receipt mismatch')
  status=venue_capture.extract(raw);status.update(source_op_id=ident,response_sha256=r['response_hash'],observed_at_utc=r['completed_at_utc'],captured_at_utc=r['completed_at_utc'])
  record('source-'+ident,{'id':ident,'request_sha256':r['request_hash'],'response_sha256':r['response_hash'],'started_at_utc':r['started_at_utc'],'completed_at_utc':r['completed_at_utc'],'actual_micro':r['actual_micro']})
  return status
 return call
