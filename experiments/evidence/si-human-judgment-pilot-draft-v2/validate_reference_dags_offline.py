import json,hashlib,math,re,html
from pathlib import Path
root=Path('/Users/rk/.codex/visualizations/2026/10/29/01a1865f-6bd2-75a2-abb1-eb14b071bbe0')
p=root/'si-human-judgment-pilot-draft-v2'
cases=json.loads((p/'candidate-cases.json').read_text())
keys=json.loads((p/'reviewer-key.json').read_text())
manifest=json.loads((p/'draft-manifest.json').read_text())
source_path=root/'anthropic-s1-pilot-20261029-v1/sec-s1-original.html'
source=html.unescape(re.sub(r'<[^>]*>',' ',source_path.read_text(errors='replace')));source=re.sub(r'\s+',' ',source)
assert hashlib.sha256(source_path.read_bytes()).hexdigest()==manifest['source_original_local_sha256']
assert len(cases)==len(keys)==12
assert {x['case_id'] for x in cases}=={x['case_id'] for x in keys}
assert sum(x['status']=='error' for x in keys)==6
assert sum(x['status']=='clean' for x in keys)==6
assert sum(x['reference_dag'] is not None for x in keys)==6
assert all(not ({'status','reference_dag','expected_review','label','answer'}&set(x)) for x in cases)
for c in cases:
 assert set(c)=={'case_id','title','question','prepared_advice','evidence','note'}
 for e in c['evidence']:
  assert set(e)=={'id','text','source','source_locator','as_of'}
  anchor=e['source_locator'].split('; find: ',1)[1]
  assert anchor.lower() in source.lower(),(c['case_id'],e['id'])

def equal(a,b):
 if isinstance(a,(int,float)) and isinstance(b,(int,float)) and not isinstance(a,bool) and not isinstance(b,bool):return math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-9)
 return a==b

def derive(g,drop_inputs=(),drop_nodes=(),changes=None):
 vals={k:v['value'] for k,v in g['inputs'].items() if k not in drop_inputs}
 vals.update(changes or {})
 built=[]
 for n in g['nodes']:
  if n['id'] in drop_nodes:continue
  assert len(n['inputs'])<=2 and len(n['inputs'])>0
  if any(i not in vals for i in n['inputs']):continue
  a,b=[vals[i] for i in n['inputs']]
  if n['op']=='add':v=a+b
  elif n['op']=='subtract':v=a-b
  elif n['op']=='divide':v=a/b
  elif n['op']=='less_than':v=a<b
  elif n['op']=='attach_right':v={'holder':b.split(' elect ')[0],'count':a}
  elif n['op']=='greater_than':
   if isinstance(b,dict):
    if b['holder']!='F/A':continue
    b=b['count']
   v=a>b
  else:raise AssertionError(n['op'])
  vals[n['id']]=v;built.append(n['id'])
 return vals.get(g['target']),built

del_checks=node_checks=counter_checks=0
for k in keys:
 g=k['reference_dag']
 if g is None:continue
 assert k['two_step_status'].startswith('bounded_formal')
 nodes=g['nodes'];target=g['target']
 depths={name:0 for name in g['inputs']}
 for node in nodes:
  assert all(parent in depths for parent in node['inputs'])
  depths[node['id']]=1+max(depths[parent] for parent in node['inputs'])
 assert depths[target]>=2,(k['case_id'],'no linked two-operation path')
 got,built=derive(g)
 assert target in built and equal(got,nodes[-1]['value']),(k['case_id'],got)
 assert len(built)>=2
 for leaf in g['critical_source_inputs']:
  result,built=derive(g,drop_inputs={leaf})
  assert target not in built and result is None,(k['case_id'],leaf)
  del_checks+=1
  result,built=derive(g,changes={leaf:g['counterfactuals'][leaf]})
  assert target not in built or not equal(result,got),(k['case_id'],leaf)
  counter_checks+=1
 for n in nodes[:-1]:
  result,built=derive(g,drop_nodes={n['id']})
  assert target not in built and result is None,(k['case_id'],n['id'])
  witness=g['excluded_node_counterexamples'][n['id']]
  changed,built_changed=derive(g,changes={witness['changed_source_input']:witness['alternative_value']})
  assert target not in built_changed or not equal(changed,got),(k['case_id'],n['id'],'invalid exclusion witness')
  node_checks+=1
 # A forged final value cannot be counted as derivation without rebuilding all declared predecessors.
 spoof,built=derive(g,drop_nodes={nodes[0]['id'],target},changes={target:got})
 assert target not in built
print(f'PASS: 12 cases; 6 error/6 clean; 6 bounded DAGs; {del_checks} critical-leaf removals; {node_checks} precursor removals; {counter_checks} counterfactual changes; 6 spoofed-target controls; all source anchors present; no network/model calls')
