from pathlib import Path
import json, hashlib
ROOT = Path('/Users/rk/.codex/visualizations/2026/10/19/01a152a3-fbde-7cc1-acdd-cb13ff14c2d9')
OUT = Path(__file__).resolve().parent
V = ROOT / 'controller-value-run-20261026-v3'
E = ROOT / 'controller-evidence-goal-20261027'
paths = {
 'worksheet': V/'applied-action-review-v1/worksheet.json',
 'value_replay': V/'main-applied-tool-responses.jsonl',
 'source_bundle': E/'source-choice-eia-18-discriminating-candidates-v5/bundle.json',
 'source_review_records': E/'eighteen-provisional-source-reviews-v1-20261027/records.json',
 'source_review_proposals': E/'source-review-seven-open-questions-v2-20261027.md',
 **{f'owner_action_{n}': V/f'guided-action-review-v1/{n}-decision.json' for n in ['0001','0003','0015']},
}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p): return json.loads(p.read_text())
def jsonl(p): return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
def unique_response(items):
    assert items, 'Missing replay response'
    unique = {json.dumps(x, sort_keys=True, ensure_ascii=False) for x in items}
    assert len(unique) == 1, 'Ambiguous replay responses for action'
    return items[0]
w = load(paths['worksheet']); replay = jsonl(paths['value_replay']); bundle = load(paths['source_bundle'])
values = [
 ('amazon_visible','action-review-e4ac13f0c32dfa582016','0001'),
 ('amazon_empty','action-review-f631edcf2063aa263293','0003'),
 ('nvidia_h100','action-review-0f8cc585997b5c46e70d','0015'),
]
cases = []
refs = []
for name, rid, owner in values:
    matches = [i for i in w['items'] if i['action_review_id'] == rid]; assert len(matches)==1
    item=matches[0]
    acts=item['available_retained_actions_before_decision']
    assert all(set(a)=={'action_id','description'} for a in acts)
    results={a['action_id']:unique_response([r['saved_response'] for r in replay if r['action_id']==a['action_id']]) for a in acts}
    initial=[{'action_id':x['action_id'], 'response':x['observed_payload']} for x in item['pre_decision_existing_evidence']]
    cases.append({'id':name,'question':item['question'],'initial_evidence':initial,'actions':[{'id':a['action_id'],'description':a['description']} for a in acts], 'saved_replay':results})
    refs.append({'case_id':name,'worksheet_action_review_id':rid,'owner_decision':str(paths['owner_action_'+owner]),'initial_evidence_field':'worksheet.items[].pre_decision_existing_evidence[].observed_payload','replay_field':'main-applied-tool-responses.jsonl saved_response matched by action_id; duplicate values must be identical'})
sourcecases=[('usgs_withdrawal','source-choice-disc-v1-8706b61ad6b3fcaac658ce1e'),('usgs_consumptive','source-choice-disc-v1-6f163022466b0539ac21bb8a'),('bea_state_gdp','source-choice-v7-df3287ee17ba8235b3df3206')]
reviews=load(paths['source_review_records'])
for name,cid in sourcecases:
    cp=[x for x in bundle['checkpoints'] if x['case_id']==cid]; assert len(cp)==1
    cp=cp[0]; inp=cp['input']; acts=inp['tool_catalog']; init=inp['initial_evidence'][:]
    preconsumed=[]
    if name=='bea_state_gdp':
        aid='action-v5-b7846a1886845ba867ba8e4f'
        a=[r for r in bundle['replay_catalog'] if r['case_id']==cid and r['action_id']==aid]; assert len(a)==1
        init.append({'action_id':aid, 'response':a[0]['saved_response']})
        preconsumed=[aid]
        acts=[a for a in acts if a['action_id'] != aid]
    results={a['action_id']:unique_response([r['saved_response'] for r in bundle['replay_catalog'] if r['case_id']==cid and r['action_id']==a['action_id']]) for a in acts}
    assert sum(1 for p in reviews['cases'] if p.get('predecessor_item',{}).get('record',{}).get('decision',{}).get('case_id')==cid)==1
    cases.append({'id':name,'question':inp['thesis'],'initial_evidence':init,'actions':[{'id':a['action_id'],'description':a['description']} for a in acts], 'saved_replay':results, 'preconsumed_action_ids':preconsumed})
    refs.append({'case_id':name,'bundle_case_id':cid,'input_version':cp['input_version'],'owner_decision':str(paths['source_review_records']),'owner_record_selector':'cases[].predecessor_item.record.decision.case_id','bea_initial_note':'A replay response shown at start and marked preconsumed; B remains available.' if preconsumed else None})
assert len(cases)==6 and len({x['id'] for x in cases})==6
for c in cases:
    aids=[a['id'] for a in c['actions']]
    assert len(aids)==len(set(aids)) and set(aids)==set(c['saved_replay'])
    assert not any(set(a)!={'id','description'} for a in c['actions'])
    assert all(a not in aids for a in c.get('preconsumed_action_ids',[]))
manifest={'schema':'controller-pilot-v2-input-manifest-v1','source_files':{k:{'path':str(p),'sha256':sha(p),'size_bytes':p.stat().st_size} for k,p in paths.items()},'case_refs':refs,'limitations':['Owner review records and old proposals are assessment references, never initial model input.','Sources contain bounded saved excerpts; absence in excerpt is not evidence of source-wide absence.','BEA starts after A; A is preconsumed and B remains available, following the predecessor replay behavior.','The 6 cases are related, previously reviewed development cases, not a blind independent holdout.']}
for file,obj in [('cases.json',{'schema':'controller-pilot-v2-cases-v1','cases':cases}),('manifest.json',manifest)]:
    (OUT/file).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
print('Built and validated',len(cases),'cases:',', '.join(c['id'] for c in cases))
for c in cases: print(c['id'],'initial',len(c['initial_evidence']),'actions',len(c['actions']),'replay',len(c['saved_replay']))
