"""Small predeclared correction of the synthetic pilot, no provider calls."""
import copy,hashlib,json
from logic_pilot.corpus import corpus as prior_corpus, canonical

def corpus():
 tasks,keys=prior_corpus();by_id={t['case_id']:t for t in tasks}
 # Predeclared mechanically: first pair and first member of second pair in
 # source generator order, independent of previous model outputs.
 selected=keys[:3];out=[];new_keys=[]
 for k in selected:
  task=copy.deepcopy(by_id[k['case_id']]);old_id=task['case_id']
  new_id='repair-'+hashlib.sha256(canonical({'schema':'universal-domain-v1','parent':old_id})).hexdigest()[:16]
  task['case_id']=new_id
  for row in task['evidence']:
   row['text']=row['text'].replace('If a creature ', 'If something ')
  task['thesis']['version']='fictional-pilot-domain-corrected-v1'
  new_key=copy.deepcopy(k);new_key['case_id']=new_id;new_key['parent_case_id']=old_id
  out.append(task);new_keys.append(new_key)
 return out,new_keys
