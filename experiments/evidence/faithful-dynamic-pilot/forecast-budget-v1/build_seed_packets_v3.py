"""Create a seed projection successor using one additional exact You response.

No network/model calls. Search snippets attributed to official URLs remain
unverified snippets; timestamps and human authorization are never inferred.
"""
from __future__ import annotations
import hashlib,json,os
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
OLD=ROOT/'forecast-seed-packets-20261029-v2'
OUT=ROOT/'forecast-seed-packets-20261029-v3'
YOU=ROOT/'forecast-source-you-20261029-01'
OLD_SHA='6afa2ac733305ab2b8f76d4959c9c60cd6ad2bd04075cac122e2c3993b4c1de6'
YOU_SHA='a1d797d3634f088a70fa4f5c1f57186e68bb3d805b010c4f3e4958670d68e152'
OP='seed-openai-you-search'
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def put(p,b):
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 fd=os.open(p.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
def build():
 old_raw=(OLD/'manifest.json').read_bytes()
 if sha(old_raw)!=OLD_SHA:raise ValueError('seed predecessor changed')
 manifest=json.loads(old_raw)
 if manifest.get('schema')!='forecast-seed-packets-v1' or len(manifest.get('cases',[]))!=4:raise ValueError('wrong predecessor')
 summary_raw=(YOU/'summary.json').read_bytes();summary=json.loads(summary_raw);record=summary.get('record',{})
 raw_path=YOU/(OP+'.raw.json');raw=raw_path.read_bytes()
 if (summary.get('status')!='completed' or summary.get('failure') is not None or sha(raw)!=YOU_SHA or
  record.get('id')!=OP or record.get('state')!='succeeded' or record.get('http_status')!=200 or
  record.get('actual_micro')!=5000 or record.get('response_sha256')!=YOU_SHA):raise ValueError('You source did not settle as recorded')
 response=json.loads(raw)
 if response.get('success') is not True:raise ValueError('source envelope failed')
 result=response['data']['results']['web'][2]
 url=result['url']
 if url!='https://openai.com/products/release-notes/':raise ValueError('unexpected source URL')
 selections=[
  ('openai-you-search-1',0,'Oct 26, 2026 · GA · GPT‑6.1 Terra is rolling out in ChatGPT Work and Codex. It supports a range of tasks, including visual reasoning, computer use, and writing.','Oct 26, 2026'),
  ('openai-you-search-2',1,'Terra is available in Work and Codex, not Chat.',None),
 ]
 evidence=[]
 for ident,index,quote,reported in selections:
  field=result['snippets'][index]
  if quote not in field:raise ValueError('excerpt not present in named source field')
  qb=quote.encode('utf-8');start=raw.find(qb)
  if start<0 or raw.count(qb)!=1 or raw[start:start+len(qb)].decode('utf-8')!=quote:raise ValueError('raw byte span absent or ambiguous')
  evidence.append({'id':ident,'text':quote,'source_url':url,
   'source_type':'search_snippet_attributed_to_official_url_not_fetched',
   'json_pointer':'/data/results/web/2/snippets/'+str(index),'raw_sha256':YOU_SHA,
   'source_effect_id':OP,'byte_offset':start,'byte_length':len(qb),
   'captured_at_utc':record['completed_at_utc'],'available_at_observed_utc':record['completed_at_utc'],
   'published_at_utc':None,'reported_date_literal':reported,
   'validation_status':'literal search-result raw substring; source page and factual correctness not independently verified'})
 OUT.mkdir(mode=0o700)
 next_manifest={**manifest,'supersedes_manifest_sha256':OLD_SHA,
  'supplemental_source_summary_path':str((YOU/'summary.json').relative_to(ROOT)),
  'supplemental_source_summary_sha256':sha(summary_raw),'cases':[]}
 for row in manifest['cases']:
  card_raw=(OLD/row['input_path']).read_bytes()
  if sha(card_raw)!=row['input_sha256']:raise ValueError('previous card changed')
  card=json.loads(card_raw);newrow=dict(row)
  if row['case_id']=='case-03':
   if card['thought']['origin']!='assistant_proposal_unaccepted' or card['thought']['human_confirmed'] is not False or card['evidence']:
    raise ValueError('unexpected case-03 predecessor')
   card['evidence']=evidence
   card['missing']=['Captured data consists of attributed search snippets; official source pages have not been fetched or verified',
    'No exact future November model announcement or release plan is established by these excerpts',
    'Exact source publication time is unknown; source-reported date is retained as text only']
   card_raw=canonical(card)
   newrow['predecessor_source']={'source_effect_id':row['source_effect_id'],'raw_path':row['raw_path'],'raw_sha256':row['raw_sha256'],'evidence_count':row['evidence_count']}
   newrow.update(source_effect_id=OP,raw_path=str(raw_path.relative_to(ROOT)),raw_sha256=YOU_SHA,evidence_count=len(evidence),input_sha256=sha(card_raw))
  put(OUT/newrow['input_path'],card_raw)
  next_manifest['cases'].append(newrow)
 put(OUT/'manifest.json',canonical(next_manifest))
 return {'manifest_sha256':sha((OUT/'manifest.json').read_bytes()),'case03_evidence_count':len(evidence)}
if __name__=='__main__':print(json.dumps(build(),ensure_ascii=False))
