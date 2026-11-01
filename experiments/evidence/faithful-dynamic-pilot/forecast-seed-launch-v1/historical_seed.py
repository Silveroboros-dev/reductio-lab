"""Verify a completed seed model phase offline, with no network or writes.

This is a review input, not a new phase authority. It requires every model
effect to have settled and every case to have a retained C and B result.
"""
from __future__ import annotations
import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-seed-launch-v1'))
import launcher,historical_five

CONTRACT_SHA='05087c585db053fd5cd8599f6491cacc8f49c6ab265f9b3418bcf71fdb07ca68'
CONTRACT=ROOT/'forecast-seed-model-contract-20261029-v1.json'
PACKET=ROOT/'forecast-seed-model-challenge-packet-v1.json'
RECEIPT=ROOT/'forecast-seed-model-challenge-receipt-v1.json'

def verify():
 """Reconcile all seed effects, outputs and shared total under shared lock."""
 ctx=launcher.verify(CONTRACT,PACKET,RECEIPT,CONTRACT_SHA);c=ctx['contract']
 source=historical_five.verify(require_seed_start_state=False)
 if source!=c['source_binding']:raise launcher.Error('seed source lineage mismatch')
 out=Path(c['execution_context']['output_root'])
 started=launcher.obj(launcher.read(out/'started.json'))
 if (started.get('contract_sha256')!=CONTRACT_SHA or started.get('challenge_sha256')!=launcher.sha(ctx['challenge_raw']) or
  started.get('receipt_sha256')!=launcher.sha(ctx['receipt_raw']) or
  started.get('case_ids')!=[x['case_id'] for x in c['task_bindings']]):raise launcher.Error('seed start marker mismatch')
 sr=launcher.read(out/'summary.json');summary=launcher.obj(sr)
 if (summary.get('requested_cases')!=4 or summary.get('attempted_cases')!=4 or summary.get('not_attempted_cases')!=0
  or summary.get('stop_index') is not None or summary.get('status')!='seed_proposals_only'
  or summary.get('post_market')!='not started' or summary.get('review')!='not human-adjudicated'):
  raise launcher.Error('seed phase incomplete or scope mismatch')
 results=summary.get('results')
 if not isinstance(results,list) or len(results)!=4:raise launcher.Error('seed results missing')
 expected_calls={}
 for i,(row,pair) in enumerate(zip(c['task_bindings'],results)):
  if (pair.get('case_id')!=row['case_id'] or pair.get('split')!=row['split'] or pair.get('task_sha256')!=row['task_sha256'] or
    launcher.obj(launcher.read(out/f'{i:02d}-pair.json'))!=pair):raise launcher.Error('seed pair binding mismatch')
  for arm in ('c','b'):
   result=pair.get(arm)
   if not isinstance(result,dict) or launcher.obj(launcher.read(out/f'{i:02d}-{arm}.json'))!=result:
    raise launcher.Error('seed arm missing')
   n=result.get('calls')
   if type(n) is not int or not 0<=n<=6:raise launcher.Error('seed call count invalid')
   expected_calls[(row['case_id'],arm)]=n
 for d in ('forecast-budget-v1','budget-v2','source-successor','model-accounting-successor'):
  sys.path.insert(0,str(ROOT/d))
 import forecast_ledger,reopen
 cfg=forecast_ledger.obj(forecast_ledger.read(ROOT/'forecast-budget-v1/ledger_contract.json'))
 base=reopen._ReadOnlyBase(Path(c['execution_context']['ledger_root']),cfg)
 try:
  forecast_ledger._check_resumable(base,cfg,historical_five.SOURCE_SHA)
  markers=base.db.execute("SELECT reason FROM run_events WHERE event='exploration_seed_started'").fetchall()
  if markers!=[(CONTRACT_SHA,)]:raise launcher.Error('seed stage identity mismatch')
  effects=base.db.execute("SELECT id,kind,state,actual_micro FROM effects WHERE kind IN ('generation','count') ORDER BY rowid").fetchall()
  expected_ids=[]
  for row in c['task_bindings']:
   for arm in ('c','b'):
    for ordinal in range(1,expected_calls[(row['case_id'],arm)]+1):
     identity=f"seed:{row['case_id']}:{arm}:{ordinal:02d}"
     expected_ids.extend([('count:'+identity,'count'),('generation:'+identity,'generation')])
  if [(e[0],e[1]) for e in effects]!=expected_ids or any(e[2]!='succeeded' or e[3] is None for e in effects):
   raise launcher.Error('seed effects do not match outcome call counts')
  state=base.summary();state['source_attempts']+=8;state['previous_source_attempts']=8
  # metadata_attempts in the base counts a distinct metadata kind; the real
  # forecast adapter counts source-category metadata. Seed has none.
  if state!=summary.get('ledger'):raise launcher.Error('seed summary and ledger disagree')
  usage=sum(e[3] for e in effects if e[1]=='generation')
 finally:base.close()
 return {'schema':'forecast-completed-seed-binding-v1','seed_contract_sha256':CONTRACT_SHA,
  'seed_challenge_sha256':launcher.sha(ctx['challenge_raw']),'seed_receipt_sha256':launcher.sha(ctx['receipt_raw']),
  'seed_summary_sha256':launcher.sha(sr),'source_binding':source,'case_ids':[x['case_id'] for x in c['task_bindings']],
  'model_generation_count':sum(expected_calls.values()),'model_usage_micro':usage,
  'ledger':state,'review_status':'not human-adjudicated; seed results are proposals'}
