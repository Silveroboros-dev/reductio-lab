"""Offline key/source/projection challenge; never invokes an inference model."""
import hashlib,html,json,math,re,sys
from pathlib import Path
p=Path(__file__).resolve().parent
root=p.parent
manifest=json.loads((p/'draft-manifest.json').read_text())
cases=json.loads((p/'candidate-cases.json').read_text())
keys=json.loads((p/'reviewer-key.json').read_text())
source_path=root/'anthropic-s1-pilot-20261029-v1/sec-s1-original.html'
source=html.unescape(re.sub(r'<[^>]*>',' ',source_path.read_text(errors='replace')))
source=re.sub(r'\s+',' ',source)
assert hashlib.sha256(source_path.read_bytes()).hexdigest()==manifest['source_original_local_sha256']
v3=root/'si-human-judgment-pilot-draft-v3'
assert hashlib.sha256((v3/'candidate-cases.json').read_bytes()).hexdigest()==manifest['predecessor_v3_candidate_sha256']
assert hashlib.sha256((v3/'reviewer-key.json').read_bytes()).hexdigest()==manifest['predecessor_v3_key_sha256']
repo_root=Path('/Users/rk/.codex/worktrees/faithful-dynamic-pilot/fitcheck-core')
for name,digest in manifest['runtime_code_sha256'].items():
 assert hashlib.sha256((repo_root/name).read_bytes()).hexdigest()==digest,(name,'runtime code drift')
for name,digest in manifest['artifact_sha256'].items():
 assert hashlib.sha256((p/name).read_bytes()).hexdigest()==digest,(name,'artifact drift')
sys.path.insert(0,str(repo_root))
from el.evals.faithful_engine.human_pilot import make_task
from el.evals.faithful_engine.engine import EngineConfig
config=EngineConfig(max_depth=2,beam_width=1,max_alternatives=1,max_selected_premises=2)
assert (config.max_depth,config.beam_width,config.max_alternatives,config.max_selected_premises)==(2,1,1,2)
assert len(cases)==len(keys)==12
bycase={c['case_id']:c for c in cases};bykey={k['case_id']:k for k in keys}
assert len(bycase)==len(bykey)==12 and set(bycase)==set(bykey)
assert sum(k['status']=='error' for k in keys)==sum(k['status']=='clean' for k in keys)==6
assert sum(k['reference_dag'] is not None for k in keys)==6
assert len({c['note'] for c in cases})==1
assert all(re.fullmatch(r'C-[0-9A-F]{6}',c['case_id']) for c in cases)
assert all(set(c)=={'case_id','title','question','prepared_advice','evidence','note'} for c in cases)
assert all(not ({'status','reference_dag','expected_review','label','answer'}&set(c)) for c in cases)
assert all(re.search(r'\bP\d{2}\b',json.dumps(c)) is None for c in cases)
order=[bykey[c['case_id']]['status'] for c in cases]
assert order[:6].count('error')==3 and all(not(order[i]==order[i+1]==order[i+2]) for i in range(10))

def same(a,b):return math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-9)
def source_number(text):
 m=re.findall(r'\$([0-9]+(?:\.[0-9]+)?) billion',text)
 assert len(m)==1,('not one source amount',text)
 return float(m[0])
def memo_number(text):
 m=re.findall(r'\$([0-9]+(?:\.[0-9]+)?) billion',text)
 assert len(m)==1,('not one memo threshold',text)
 return float(m[0])
def derive(g,projection,drop_nodes=(),inject=None):
 vals={}
 for ident,entry in g['inputs'].items():
  if ident in projection:
   vals[ident]=source_number(projection[ident]) if entry['role']=='primary_source' else memo_number(projection[ident])
 vals.update(inject or {})
 built=[]
 for node in g['nodes']:
  if node['id'] in drop_nodes or any(x not in vals for x in node['inputs']):continue
  x,y=[vals[z] for z in node['inputs']]
  if node['op']=='add':v=x+y
  elif node['op']=='subtract':v=x-y
  elif node['op']=='less_than':v=x<y
  elif node['op']=='greater_than':v=x>y
  else:raise AssertionError(node['op'])
  vals[node['id']]=v;built.append(node['id'])
 return vals.get(g['target']),built,vals.get('node:0001')
def check_binding(binding):
 pos=source.find(binding['section_start']);assert pos>=0
 window=source[pos:pos+binding['window_chars']]
 assert binding['period_marker'] in window
 if binding['kind']=='prose':assert binding['atomic_source_phrase'] in window
 else:
  i=window.find(binding['row_label']);j=window.find(binding['next_row_label'],i+len(binding['row_label']))
  assert i>=0 and j>i and window[i:j].strip().endswith(binding['atomic_source_cell'])

source_atoms=source_deletions=memo_deletions=source_flips=memo_flips=node_deletions=spoof_controls=adapter_projections=0
for c in cases:
 assert all(set(e)=={'id','text','source','source_locator','as_of'} for e in c['evidence'])
 assert all(re.fullmatch(r'E-[0-9A-F]{8}',e['id']) for e in c['evidence'])
 task=make_task(c,user_values='No additional priorities supplied for this offline projection check.',initial_view='unknown',as_of_utc='2026-10-30T00:00:00Z',source_snapshot_sha256=manifest['source_original_local_sha256'])
 adapter_projections+=1
 actual={e['id']:e for e in task['evidence']}
 memo_id=c['case_id']+'-ADVICE'
 assert actual[memo_id]['kind']=='quote' and actual[memo_id]['text']=='Simulated advisory claim, unverified: '+c['prepared_advice']
 assert set(actual)=={memo_id}|{e['id'] for e in c['evidence']}
 k=bykey[c['case_id']];g=k['reference_dag']
 if g is None:
  for item in c['evidence']:
   assert '; find: ' in item['source_locator']
   anchor=item['source_locator'].split('; find: ',1)[1]
   assert anchor.lower() in source.lower(),(c['case_id'],item['id'],'non-DAG source anchor')
  continue
 assert len(c['evidence'])==2
 source_ids=[e['id'] for e in c['evidence']]
 assert len(set(source_ids))==2 and set(k['source_bindings_reviewer_only'])==set(source_ids)
 assert len(g['inputs'])==3 and set(g['inputs'])==set(source_ids)|{memo_id}
 assert g['inputs'][memo_id]['role']=='unverified_memo_claim'
 assert g['inputs'][memo_id]['text']==actual[memo_id]['text']
 assert len(g['nodes'])==2 and [n['id'] for n in g['nodes']]==['node:0001','node:0002'] and g['target']=='node:0002'
 assert set(g['nodes'][0]['inputs'])==set(source_ids)
 assert g['nodes'][1]['inputs']==['node:0001',memo_id]
 shape=g['engine_shape']
 assert (shape['max_depth'],shape['beam_width'],shape['max_premise_ids_per_inference'],shape['ordered_local_inferences'],shape['source_leaf_count'],shape['memo_leaf_count'])==(2,1,2,2,2,1)
 assert shape['step1_selected_ids']==g['nodes'][0]['inputs'] and shape['step2_selected_ids']==g['nodes'][1]['inputs']
 for sid in source_ids:
  assert g['inputs'][sid]['role']=='primary_source'
  assert same(g['inputs'][sid]['value'],source_number(actual[sid]['text']))
  check_binding(k['source_bindings_reviewer_only'][sid]);source_atoms+=1
 assert same(g['inputs'][memo_id]['value'],memo_number(actual[memo_id]['text']))
 projection={ident:item['text'] for ident,item in actual.items()}
 result,built,n1=derive(g,projection)
 assert built==['node:0001','node:0002'] and same(n1,g['nodes'][0]['value']) and result is g['nodes'][1]['value']
 assert result is (k['status']=='clean')
 assert all(not same(n1,g['inputs'][sid]['value']) for sid in source_ids)
 assert not same(n1,g['inputs'][memo_id]['value'])
 # Neither intermediate amount nor answer token may be handed to the model in source/advice text.
 visible=' '.join(item['text']+' '+item.get('source','') for item in actual.values())+' '+c['question']
 token=f'{n1:.3f}'.rstrip('0').rstrip('.')
 assert re.search(r'(?<![0-9.])'+re.escape(token)+r'(?![0-9.])',visible) is None,(c['case_id'],'n1 leakage')
 assert re.search(r'\b(?:true|false)\b',visible,re.I) is None,(c['case_id'],'n2 leakage')
 for sid in source_ids:
  reduced=dict(projection);del reduced[sid]
  out,built,_=derive(g,reduced)
  assert out is None and 'node:0002' not in built
  source_deletions+=1
  alt=g['source_counterfactuals'][sid]
  changed=dict(projection);old=changed[sid];match=re.search(r'\$[0-9]+(?:\.[0-9]+)? billion',old)
  assert match
  changed[sid]=old[:match.start()]+f'${alt:g} billion'+old[match.end():]
  out,built,_=derive(g,changed)
  assert built==['node:0001','node:0002'] and out is not result
  source_flips+=1
 reduced=dict(projection);del reduced[memo_id]
 out,built,_=derive(g,reduced)
 assert out is None and 'node:0001' in built and 'node:0002' not in built
 memo_deletions+=1
 alt=g['memo_counterfactual']['new_threshold'];changed=dict(projection);old=changed[memo_id];match=re.search(r'\$[0-9]+(?:\.[0-9]+)? billion',old);assert match
 changed[memo_id]=old[:match.start()]+f'${alt:g} billion'+old[match.end():]
 out,built,_=derive(g,changed)
 assert built==['node:0001','node:0002'] and out is not result
 memo_flips+=1
 out,built,_=derive(g,projection,drop_nodes={'node:0001'})
 assert out is None and 'node:0002' not in built
 node_deletions+=1
 out,built,_=derive(g,projection,drop_nodes={'node:0001','node:0002'},inject={'node:0002':result})
 assert out is result and 'node:0002' not in built
 spoof_controls+=1
print(f'PASS v4 bytes: {adapter_projections} actual make_task projections; 6 two-inference/2-source-plus-unverified-memo DAGs; {source_atoms} period-bound source atoms; {source_deletions} source-ID deletions; {memo_deletions} memo-ID deletions; {source_flips} source counterfactual verdict flips; {memo_flips} memo-claim verdict flips; {node_deletions} node deletions; {spoof_controls} forged-target controls; 6 error/6 clean; no model/provider calls')
