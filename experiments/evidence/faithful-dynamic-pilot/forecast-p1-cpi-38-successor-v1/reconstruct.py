"""Offline reconstruction of completed CPI B/no-news from stopped journal."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for name in ('forecast-p1-cpi-resumed-v1','forecast-p1-cpi-recovery-v1','forecast-controller-v1'):
 sys.path.insert(0,str(ROOT/name))
import history,admission_evidence,forecast,gate,replay
PARENT=ROOT/'forecast-cpi-p1-format-recovery-ledger-20261029-01/ledger.sqlite3'
PARENT_SHA='951c2a23c8b320930404420098aacaf0e47a1ae6978521d3a6877e425b212417'
EXPECTED_B_SHA='4a84a3921d2a612acbd30ad072ba490b5d8064cac17959b0ea09a46aa7f7b896'
REPAIR_SHA='c4e94fc345fc1d671b9a56cd8af9b8eb08784131a7c8fcf49ceb4c303c0ebd33'
class Error(ValueError):pass

def baseline():
 hist=history.History(PARENT,PARENT_SHA);pre=admission_evidence.inspect();task=pre['admission']['bundle']['tasks']['b_no_news'];n=0
 def from_saved(stage,payload):
  nonlocal n
  n+=1;req=forecast.build_request(stage,payload);ident=f'p1:case-02:no_news:b:{n:02d}';count=hist.inspect('count:'+ident,req);gen=hist.inspect('generation:'+ident,req)
  if count['classification']!='success' or gen['classification']!='success' or gen['related_id']!=count['id']:raise Error('B count/generation receipt mismatch')
  return forecast.parse_response(json.loads(gen['response']))
 engine=forecast.BaselineEngine(from_saved,matched_calls=8);out=engine.run(task)
 if n!=8 or out.get('status')!='proposal' or out.get('calls')!=8 or gate.sha(gate.canonical(out))!=EXPECTED_B_SHA:raise Error('B reconstruction mismatch')
 return out

def bundle():
 b=baseline();c=replay.repaired_outcome()
 if gate.sha(gate.canonical(c))!=REPAIR_SHA:raise Error('C posthoc derivative changed')
 return {'schema':'cpi-p1-no-news-reconstruction-v1','parent_db_sha256':PARENT_SHA,'c_repair_sha256':REPAIR_SHA,
  'b_outcome_sha256':EXPECTED_B_SHA,'b_no_news':b,'c_no_news_posthoc':c,
  'qualification':'C raw formatter failed strict JSON. C displayed value is an exact one-character posthoc format repair; B was reconstructed from all eight successful raw responses. No model/source calls occurred.'}
