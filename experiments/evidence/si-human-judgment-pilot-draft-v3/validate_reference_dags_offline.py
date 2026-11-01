import json,hashlib,math,re,html
from pathlib import Path
root=Path('/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0')
p=root/'si-human-judgment-pilot-draft-v3'
cases=json.loads((p/'candidate-cases.json').read_text());keys=json.loads((p/'reviewer-key.json').read_text());manifest=json.loads((p/'draft-manifest.json').read_text())
source_path=root/'anthropic-s1-pilot-20261029-v1/sec-s1-original.html'
source=html.unescape(re.sub(r'<[^>]*>',' ',source_path.read_text(errors='replace')));source=re.sub(r'\s+',' ',source)
assert hashlib.sha256(source_path.read_bytes()).hexdigest()==manifest['source_original_local_sha256']
v2=root/'si-human-judgment-pilot-draft-v2'
assert hashlib.sha256((v2/'candidate-cases.json').read_bytes()).hexdigest()==manifest['predecessor_v2_candidate_sha256']
assert hashlib.sha256((v2/'reviewer-key.json').read_bytes()).hexdigest()==manifest['predecessor_v2_key_sha256']
assert len(cases)==len(keys)==12
bycase={c['case_id']:c for c in cases};bykey={k['case_id']:k for k in keys}
assert set(bycase)==set(bykey) and len(bycase)==12
assert sum(k['status']=='error' for k in keys)==sum(k['status']=='clean' for k in keys)==6
assert sum(k['reference_dag'] is not None for k in keys)==6
assert all(re.fullmatch(r'C-[0-9A-F]{6}',x) for x in bycase)
assert len({c['note'] for c in cases})==1
for c in cases:
 assert set(c)=={'case_id','title','question','prepared_advice','evidence','note'}
 assert not ({'status','reference_dag','expected_review','label','answer'}&set(c))
 assert re.search(r'\bP\d{2}\b',json.dumps(c)) is None
 assert all(set(e)=={'id','text','source','source_locator','as_of'} for e in c['evidence'])
 assert all(re.fullmatch(r'E-[0-9A-F]{8}',e['id']) for e in c['evidence'])
 assert all(e['source'].startswith('https://www.sec.gov/Archives/edgar/') for e in c['evidence'])

def same(a,b):
 if isinstance(a,(int,float)) and not isinstance(a,bool) and isinstance(b,(int,float)) and not isinstance(b,bool):
  return math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-9)
 return a==b

def visible_number(text):
 money=re.findall(r'\$([0-9]+(?:\.[0-9]+)?) billion',text)
 if money:
  assert len(money)==1,('multiple monetary atoms',text)
  return float(money[0])
 # The only non-monetary DAG is a seat-count case; every text has exactly one seat numeral.
 nums=re.findall(r'(?<![A-Za-z0-9])([0-9]+)(?![A-Za-z0-9])',text)
 assert len(nums)==1,('multiple numeric atoms',text)
 return int(nums[0])

def derive(g,projection,drop_nodes=(),injected=None):
 vals={}
 for name,leaf in g['inputs'].items():
  eid=leaf['evidence']
  if eid in projection:vals[name]=visible_number(projection[eid])
 vals.update(injected or {})
 built=[]
 for n in g['nodes']:
  if n['id'] in drop_nodes or any(x not in vals for x in n['inputs']):continue
  x,y=[vals[z] for z in n['inputs']]
  if n['op']=='add':v=x+y
  elif n['op']=='subtract':v=x-y
  elif n['op']=='divide':v=x/y
  elif n['op']=='equal':v=same(x,y)
  else:raise AssertionError(n['op'])
  vals[n['id']]=v;built.append(n['id'])
 return vals.get('n2'),built

def memo_true(result,predicate):
 if predicate['op']=='greater_than':return result>predicate['threshold']
 if predicate['op']=='less_than':return result<predicate['threshold']
 raise AssertionError(predicate)

def check_binding(binding):
 at=source.find(binding['section_start']);assert at>=0
 window=source[at:at+binding['window_chars']]
 assert binding['period_marker'] in window
 if binding['kind']=='prose':assert binding['atomic_source_phrase'] in window
 else:
  i=window.find(binding['row_label']);j=window.find(binding['next_row_label'],i+len(binding['row_label']))
  assert i>=0 and j>i
  assert window[i:j].strip().endswith(binding['atomic_source_cell'])

atom_count=leaf_deletions=counterfactual_flips=node_deletions=spoof_controls=0
for k in keys:
 g=k['reference_dag']
 if g is None:continue
 c=bycase[k['case_id']];evidence={e['id']:e for e in c['evidence']};projection={eid:e['text'] for eid,e in evidence.items()}
 assert len(evidence)==len(g['inputs'])==3
 assert set(evidence)==set(k['source_bindings_reviewer_only'])
 assert set(g['inputs'])=={'a','b','c'}
 assert len(g['nodes'])==2 and [n['id'] for n in g['nodes']]==['n1','n2'] and g['target']=='n2'
 assert g['nodes'][0]['inputs']==['a','b'] and set(g['nodes'][1]['inputs'])=={'n1','c'}
 assert all(len(n['inputs'])==2 for n in g['nodes'])
 shape=g['engine_shape']
 assert (shape['max_depth'],shape['beam_width'],shape['max_premise_ids_per_inference'],shape['ordered_local_inferences'],shape['distinct_source_leaves_in_ancestry'])==(2,1,2,2,3)
 assert shape['step1_parents']==['a','b'] and shape['step2_parents']==g['nodes'][1]['inputs']
 for name,leaf in g['inputs'].items():
  eid=leaf['evidence'];assert eid in evidence
  assert same(visible_number(projection[eid]),leaf['value'])
  check_binding(k['source_bindings_reviewer_only'][eid])
  atom_count+=1
 target,built=derive(g,projection)
 assert built==['n1','n2'] and same(target,g['nodes'][-1]['value']),(k['case_id'],'value')
 # Final target is not verbatim in any participant-side evidence or memo.
 visible=' '.join(projection.values())+' '+c['prepared_advice']
 if isinstance(target,float):
  assert re.search(r'(?<![0-9.])'+re.escape(str(round(target,3)))+r'(?![0-9.])',visible) is None
 elif isinstance(target,int):
  assert re.search(r'(?<![0-9])'+str(target)+r'(?![0-9])',visible) is None
 baseline=memo_true(target,g['memo_check_reviewer_only'])
 assert baseline==(k['status']=='clean'),(k['case_id'],'memo truth vs label')
 for name,leaf in g['inputs'].items():
  reduced=dict(projection);del reduced[leaf['evidence']]
  out,built=derive(g,reduced)
  assert out is None and 'n2' not in built,(k['case_id'],name,'projection deletion')
  # Change only the model-visible atomic fact, with every other evidence ID unchanged.
  alt=g['counterfactuals'][name]
  altered=dict(projection);oldtext=altered[leaf['evidence']]
  if '$' in oldtext:
   token=re.search(r'\$[0-9]+(?:\.[0-9]+)? billion',oldtext).group(0)
   replacement=f'${alt:g} billion'
  else:
   token=re.search(r'(?<![A-Za-z0-9])[0-9]+(?![A-Za-z0-9])',oldtext).group(0)
   replacement=str(alt)
  altered[leaf['evidence']]=oldtext.replace(token,replacement,1)
  changed,changed_built=derive(g,altered)
  assert changed_built==['n1','n2'] and not same(changed,target)
  assert memo_true(changed,g['memo_check_reviewer_only'])!=baseline,(k['case_id'],name,'memo classification witness')
  leaf_deletions+=1;counterfactual_flips+=1
 # With the first derived node omitted, no valid second inference exists.
 assert g['nodes'][1]['inputs'].count('n1')==1
 out,built=derive(g,projection,drop_nodes={'n1'})
 assert out is None and 'n2' not in built
 node_deletions+=1
 # An injected target value is not a constructed inference when both declared nodes are absent.
 out,built=derive(g,projection,drop_nodes={'n1','n2'},injected={'n2':target})
 assert same(out,target) and 'n2' not in built
 spoof_controls+=1
print(f'PASS: 12 neutral-ID mixed cases, 6 error/6 clean; 6 DAGs exactly 2 sequential binary inferences and 3 atomically source-bound visible facts; {atom_count} source cells/phrases, {leaf_deletions} evidence-ID deletion failures, {counterfactual_flips} memo-classification flip witnesses, {node_deletions} node-deletion checks, {spoof_controls} forged-target controls; no network/model calls')
