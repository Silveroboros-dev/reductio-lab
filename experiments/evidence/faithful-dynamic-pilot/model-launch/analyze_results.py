"""Summarize saved experiment slot files without opening live ledger or effects.

No semantic labels are adjudicated. Missing/in-progress slots are not counted as
failures. Read-only, no network. A final ledger summary is reported only when
runner has saved it; it is not by itself the provider's independent invoice.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path

def row(result):
    outcome=result.get('outcome') or {}
    events=outcome.get('events') or outcome.get('trace') or result.get('partial_trace') or []
    events=[e for e in events if isinstance(e,dict)]
    selected=outcome.get('selected_action_id')
    if selected is None:
        selections=[e.get('action_id') for e in events if e.get('event') in ('source_replayed','query_selected')]
        selected=selections[0] if selections else None
    choices=[{'action':e.get('action'), 'action_id':e.get('action_id'), 'expectation_recorded':bool(e.get('expectation'))} for e in events if e.get('event')=='source_decision']
    source_proposals=[]
    for e in events:
        if e.get('stage') in ('source_selection','reflect','self_check') and e.get('event') in ('model_returned','generation_returned'):
            decision=e.get('output',e.get('result'))
            if isinstance(decision,dict):source_proposals.append({'stage':e['stage'],'action':decision.get('action'),'action_id':decision.get('action_id'),'expectation_recorded':bool(decision.get('expectation'))})
    answers=outcome.get('proposed_answers')
    if answers is None:answers=(outcome.get('result') or {}).get('answers',[])
    answers=[{'contract_id':a.get('contract_id'),'label':a.get('label'),'citations':a.get('citations',[]),'explanation':a.get('explanation')} for a in answers if isinstance(a,dict)] if isinstance(answers,list) else []
    calls=outcome.get('calls',outcome.get('model_calls'))
    if calls is None:calls=sum(e.get('event') in ('model_started','generation_started') for e in events)
    return {'slot':result.get('slot'),'case_id':result.get('case_id'),'arm':result.get('arm'),
        'status':result.get('semantic_status',result.get('status',outcome.get('status'))),
        'outcome_status':outcome.get('status'),'reason':outcome.get('reason',result.get('error_type')),
        'source_selected':selected,'source_decision':choices,'model_source_proposals':source_proposals,'model_calls_recorded':calls,'answers':answers,
        'source_conflicts':result.get('unresolved_source_conflicts',[])}

def analyze(root):
    root=Path(root); schedule=json.loads((root/'schedule.json').read_bytes()); rows=[]
    for i,item in enumerate(schedule):
        path=root/f'{i:02d}.json';started=(root/f'{i:02d}-started.json').exists()
        if path.is_file():
            try:data=json.loads(path.read_bytes())
            except (ValueError,OSError):data=None
            if isinstance(data,dict):rows.append(row(data));continue
        rows.append({'slot':i,'case_id':item['case_id'],'arm':item['arm'],'status':'in_progress' if started else 'not_started','answers':[]})
    summary_path=root/'summary.json'
    try:summary=json.loads(summary_path.read_bytes()) if summary_path.is_file() else None
    except (ValueError,OSError):summary=None
    source_manifest_path=root.parent/'source-receipt-manifest-20261029.json'
    source_spend=None
    try:
        records=json.loads(source_manifest_path.read_bytes())['records']
        if len(records)==8 and {x['id'] for x in records}=={f'source:case-{i:02}:serper' for i in range(1,9)} and all(type(x['actual_micro']) is int and x['actual_micro']>=0 for x in records):
            source_spend=sum(x['actual_micro'] for x in records)
    except (ValueError,OSError,KeyError,TypeError): pass
    return {'review':'unreviewed model proposals; no independent pair-label assessment',
            'rows':rows,'saved_slots':sum(x['status'] not in ('in_progress','not_started') for x in rows),
            'total_slots':len(rows),'final_ledger_summary':summary.get('ledger') if isinstance(summary,dict) else None,
            'source_expense_micro_usd':source_spend,'ledger_caveat':'Model charges and uncertain reserves available only after final durable ledger summary; no independent bill reconciliation.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('run_dir',type=Path);args=parser.parse_args()
    print(json.dumps(analyze(args.run_dir),ensure_ascii=False,sort_keys=True,indent=2))
