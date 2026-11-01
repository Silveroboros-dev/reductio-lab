"""Frozen, synthetic four-hop logical worlds; no network or model access."""
from __future__ import annotations
import hashlib, json, random

SEED=2026102901
SCENARIOS=[
 ('Ignis', 'a dragon', 'eats only mountain moss', 'has no iron-tipped armour', 'is allergic to silver bells'),
 ('Luma', 'a griffin', 'eats only river lilies', 'has no copper-tipped armour', 'is allergic to bronze bells'),
 ('Tarek', 'a wyvern', 'eats only silver clover', 'has no tin-tipped armour', 'is allergic to crystal bells'),
 ('Neri', 'a manticore', 'eats only yellow algae', 'has no lead-tipped armour', 'is allergic to wooden bells'),
]
COLORS=['amber','azure','bronze','coral','emerald','golden','indigo','jade','lilac','maroon','ochre','pearl','russet','saffron','teal','violet','yellow','zinc','ivory','navy','cobalt','pink','umber','white','silver','black','plum','grey','scarlet','aqua','olive','rose']
ANIMALS=['owl','otter','badger','moth','fox','goat','seal','deer','stoat','mouse','eagle','crane','ibis','lynx','boar','swan','koala','horse','mule','shark','frog','weasel','quail','crow','beaver','bison','yak','hare','wolf','lemur','cat','vole']

def canonical(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def digest(v):return hashlib.sha256(canonical(v)).hexdigest()

def corpus():
 tasks=[];keys=[]
 for family,(name,p0,p1,p2,p3) in enumerate(SCENARIOS):
  for polarity in (True,False):
   # Counterfactual pair differs only in the final rule; presentation shuffle identical.
   rng=random.Random(SEED+family)
   items=[('fact',p0,None,f'{name} is {p0}.'),
          ('rule',p0,p1,f'If a creature is {p0}, then it {p1}.'),
          ('rule',p1,p2,f'If a creature {p1}, then it {p2}.'),
          ('rule',p2,p3,f'If a creature {p2}, then it {p3}.')]
   target='is authorized to enter the sanctuary' if polarity else 'is not authorized to enter the sanctuary'
   items.append(('rule',p3,target,f'If a creature {p3}, then it {target}.'))
   # Some distractors apply to p0 but cannot imply either target; others are unrelated.
   n=16 if family<2 else 32
   for i in range(n):
    article='an' if COLORS[i][0] in 'aeiou' else 'a'
    left=p0 if i%2==0 else f'is {article} {COLORS[i]} {ANIMALS[i]}'
    right=f'carries a {COLORS[(i+7)%32]} ribbon'
    condition=f'is {p0}' if i%2==0 else left
    items.append(('rule',left,right,f'If a creature {condition}, then it {right}.'))
   rng.shuffle(items)
   evidence=[];facts=[];rules=[]
   for i,(kind,left,right,text) in enumerate(items):
    ident=f's{i:03d}'
    evidence.append({'id':ident,'kind':'observation','source':'fictional statements supplied in task','text':text})
    if kind=='fact':facts.append((left,ident))
    else:rules.append((left,right,ident))
   question=(f'In this fictional world, is {name} authorized to enter the sanctuary? '
             'Use only the supplied statements, without real-world assumptions. '
             'Answer YES if authorization follows, NO if non-authorization follows, '
             'or UNKNOWN if neither follows. Briefly explain your reasoning.')
   case_id='case-' + hashlib.sha256(f'{SEED}:{family}:{int(polarity)}'.encode()).hexdigest()[:16]
   task={'case_id':case_id,'task_type':'exploration','question':question,
         'thesis':{'text':question,'version':'fictional-pilot-v1','origin':'pre-registered synthetic research task'},
         'required_questions':[{'id':'user-target','question':question,'evidence_ids':[]}], 'evidence':evidence}
   closure={p:0 for p,_ in facts}; proof={p:[fid] for p,fid in facts}
   changed=True
   while changed:
    changed=False
    for a,b,rid in rules:
     if a in closure and b not in closure:
      closure[b]=closure[a]+1;proof[b]=proof[a]+[rid];changed=True
   yes='is authorized to enter the sanctuary' in closure;no='is not authorized to enter the sanctuary' in closure
   if yes==no or yes!=polarity or closure[target]!=4 or len(proof[target])!=5: raise ValueError('ambiguous or non-four-hop item')
   tasks.append(task);keys.append({'case_id':case_id,'answer':'YES' if polarity else 'NO','proof_ids':proof[target],'inference_depth':4,'distractors':n})
 # Fixed counterbalancing order doesn't group positive or negative outcomes.
 random.Random(SEED+999).shuffle(tasks)
 return tasks,keys
