"""Twelve predeclared finite universal-implication tasks; no model/network."""
from __future__ import annotations
import hashlib,json,random,string
from collections import deque

SEED=202610292017

def canonical(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def digest(x):return hashlib.sha256(canonical(x)).hexdigest()

def _labels(rng,n):
 seen=set();out=[]
 while len(out)<n:
  x=''.join(rng.choice(string.ascii_uppercase) for _ in range(5))
  if x not in seen:seen.add(x);out.append(x)
 return out

def _closure(start, rules):
 edges={}
 for source,target,ident in rules:edges.setdefault(source,[]).append((target,ident))
 found={start:(0,[])};q=deque([start])
 while q:
  source=q.popleft();depth,prior=found[source]
  for target,ident in edges.get(source,[]):
   if target not in found:
    found[target]=(depth+1,prior+[ident]);q.append(target)
 return found

def build():
 tasks=[];keys=[];pairs=[]
 for family in range(6):
  rng=random.Random(SEED+family)
  words=_labels(rng, 12 + (64 if family<3 else 128))
  yes_chain,no_chain=words[:6],words[6:12]
  distractor_count=64 if family<3 else 128
  branches=distractor_count//8;pool=words[12:]; rules=[]
  for chain,outcome in ((yes_chain,'AUTHORIZED'),(no_chain,'NOT_AUTHORIZED')):
   for i in range(5):rules.append((chain[i],chain[i+1]))
   rules.append((chain[5],outcome))
  # Branches from main-chain predicates lead to seven unique decoys and a cycle;
  # they never join a target-producing chain or a target terminal.
  for b in range(branches):
   nodes=pool[b*8:(b+1)*8];anchors=yes_chain[:5]+no_chain[:5]
   previous=anchors[(b*3+family)%len(anchors)]
   for j in range(7):rules.append((previous,nodes[j]));previous=nodes[j]
   rules.append((previous,nodes[2]))
  assert len(rules)==12+distractor_count
  entries=[{'type':'fact','source':'@START','target':None}]+[{'type':'rule','source':a,'target':b} for a,b in rules]
  random.Random(SEED+1000+family).shuffle(entries)
  subject=f'Entity-{family+1}'
  case_ids=[]
  for correct,start in (('YES',yes_chain[0]),('NO',no_chain[0])):
   rows=[];formal=[];fact_id=None
   for n,item in enumerate(entries):
    ident=f's{n:03d}'
    if item['type']=='fact':
     fact_id=ident;text=f'{subject} has label {start}.'
    else:
     src,tgt=item['source'],item['target'];formal.append((src,tgt,ident))
     if tgt=='AUTHORIZED':tail='is authorized to enter the sanctuary'
     elif tgt=='NOT_AUTHORIZED':tail='is not authorized to enter the sanctuary'
     else:tail=f'has label {tgt}'
     text=f'If something has label {src}, then it {tail}.'
    rows.append({'id':ident,'kind':'observation','source':'fictional task statements','text':text})
   closure=_closure(start,formal);yes=closure.get('AUTHORIZED');no=closure.get('NOT_AUTHORIZED')
   if correct=='YES':valid=yes is not None and yes[0]==6 and no is None; proof=yes
   else:valid=no is not None and no[0]==6 and yes is None;proof=no
   if not valid:raise ValueError('invalid key, conflicting target or depth')
   question=(f'In this fictional world, is {subject} authorized to enter the sanctuary? '
      'Use only the supplied universal rules and the supplied initial fact; ignore real-world assumptions. '
      'Answer YES if authorization follows, NO if non-authorization follows, or UNKNOWN if neither follows. '
      'Give a brief explanation based on the supplied statement IDs.')
   identity={'question':question,'evidence':rows};case_id='hard-'+digest(identity)[:20]
   task={'case_id':case_id,'task_type':'exploration','question':question,
      'thesis':{'text':question,'version':'hard-si-pilot-v1','origin':'synthetic research task'},
      'required_questions':[{'id':'user-target','question':question,'evidence_ids':[]}], 'evidence':rows}
   correct_rule=proof[1][-1];rule=next((a,b) for a,b,i in formal if i==correct_rule)
   key={'case_id':case_id,'answer':correct,'proof_ids':[fact_id]+proof[1],
        'proof_depth':proof[0],'distractors':distractor_count,
        'initial_label':start,'terminal_rule_id':correct_rule,
        'terminal_condition':rule[0], 'terminal_text':next(x['text'] for x in rows if x['id']==correct_rule)}
   tasks.append(task);keys.append(key);case_ids.append(case_id)
  pairs.append({'pair_index':family+1,'case_ids':case_ids,'distractors':distractor_count})
 return tasks,keys,pairs
