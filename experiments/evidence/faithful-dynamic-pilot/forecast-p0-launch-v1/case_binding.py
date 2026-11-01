"""Reconstruct and bind the exact candidate p0 cases; no providers or ledger."""
import copy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-p0-launch-v1'))
import approved_inputs as a,create_cases,p0_launcher as p

MANIFEST='9ad9c5d2548bf821d819e2b3e45d4e3328c5a6f261c631a88ef2ec0bb46fd073'

def prepare(*,clock):
 base=ROOT/'forecast-p0-cases-20261029-v2';mr=p._read(base/'manifest.json')
 if p.o.sha(mr)!=MANIFEST:raise p.Error('p0 candidate manifest drift')
 m=p._json(mr)
 if m.get('schema')!='forecast-p0-case-candidates-v1' or m.get('status')!='candidate_not_yet_independently_reviewed_or_authorized_for_dispatch':raise p.Error('candidate status mismatch')
 original=a.build(m['common_as_of_utc'],verify_human_origin=create_cases.decision_check,verify_relays_and_fit=create_cases.relay_check)
 if len(m['case_bindings'])!=len(original):raise p.Error('case count drift')
 byid={c['case_id']:c for c in original};bind={x['case_id']:x for x in m['case_bindings']}
 if len(byid)!=4 or set(byid)!=set(bind):raise p.Error('case identity drift')
 paths=[]
 for case in original:
  cid=case['case_id'];b=bind[cid];expected=base/(cid+'.json');raw=p._read(expected)
  if (b['path']!=str(expected) or b['raw_sha256']!=p.o.sha(raw) or p._json(raw)!=case):raise p.Error('candidate differs from reconstructed inputs')
  paths.append(str(expected))
 def verify_record(path,raw):
  cid=Path(path).stem
  return cid in byid and path==bind[cid]['path'] and p.o.sha(raw)==bind[cid]['raw_sha256'] and p._json(raw)==byid[cid]
 def verify_case(case):return case.get('case_id') in byid and case==byid[case['case_id']]
 bundle=p.prepare(paths,verify_case_record=verify_record,verify_human=verify_case,
  verify_rules=verify_case,verify_evidence=verify_case,clock=clock)
 for got in bundle['prepared']:
  row=bind[got['case']['case_id']]
  if got['case_sha256']!=row['case_sha256'] or got['task_sha256']!=row['task_sha256']:raise p.Error('task projection drift')
 return bundle
