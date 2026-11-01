"""Receipt-bound Orthogonal market observation; freshness limited by gateway.

This does not claim a direct request to Kalshi or establish an upstream cache
age. No network calls; current source ledger is opened read-only per check.
"""
import copy,json,sqlite3
import gate,conditional_capture
class Error(ValueError):pass

def extract(raw):
 try:
  d=json.loads(raw)
  if d.get('success') is not True or not isinstance(d['data']['markets'],list):raise Error('missing venue markets')
  matches=[m for m in d['data']['markets'] if isinstance(m,dict) and m.get('ticker')==gate.TICKER]
  if len(matches)!=1:raise Error('venue ticker not unique')
  m=matches[0]
  if not isinstance(m.get('status'),str) or not isinstance(m.get('result'),str) or not isinstance(m.get('rules_primary'),str) or not isinstance(m.get('rules_secondary'),str):raise Error('venue status or rules incomplete')
  return {'contract_id':gate.TICKER,'state':m['status'],'result':m['result'],'rules_primary':m['rules_primary'],'rules_secondary':m['rules_secondary']}
 except (KeyError,ValueError,TypeError):raise Error('unparseable venue observation') from None

def decode(raw,receipt,op):
 # Price and other new market data are deliberately excluded from status.
 return extract(raw)

def verify_status(status,case,at):
 try:
  op_id=status['source_op_id'];response_hash=status['response_sha256']
  contract_bytes=conditional_capture.CONTRACT.read_bytes()
  if gate.sha(contract_bytes)!=conditional_capture.SOURCE_CONTRACT_SHA:return False
  contract=json.loads(contract_bytes);ops=[x for x in contract['operations'] if x['kind']=='status_refresh' and x['ticket']['id']==op_id]
  if len(ops)!=1:return False
  op=ops[0];db=sqlite3.connect('file:'+str(conditional_capture.DB)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
  try:row=db.execute('select * from effects where id=?',(op_id,)).fetchone()
  finally:db.close()
  if row is None:return False
  row=dict(row);raw=bytes(row['response']);req=gate.canonical(op['payload'])
  if (row['kind'],row['provider'],row['endpoint'],row['state'],row['http_status'])!=('source','orthogonal','/v1/run','succeeded',200):return False
  if bytes(row['request'])!=req or row['request_hash']!=gate.sha(req) or row['response_hash']!=response_hash or gate.sha(raw)!=response_hash or row['actual_micro'] is None:return False
  decoded=extract(raw)
  if any(status.get(k)!=v for k,v in decoded.items()) or status['observed_at_utc']!=row['completed_at_utc'] or status['captured_at_utc']!=row['completed_at_utc']:return False
  if status['state']!='active' or status['result']!='' or status['rules_primary']!=case['rules_primary'] or status['rules_secondary']!=case['rules_secondary']:return False
  observed=gate.o.instant(status['captured_at_utc']);now=gate.o.instant(at)
  return observed<=now and 0<=(now-observed).total_seconds()<=300
 except (KeyError,ValueError,TypeError,sqlite3.Error,Error,gate.o.EligibilityError):return False
