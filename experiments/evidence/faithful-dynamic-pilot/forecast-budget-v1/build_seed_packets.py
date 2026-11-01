"""Project exact public-source substrings into four private seed packets.

No network, model, secrets or edits to raw receipts. New questions are explicitly
operator proposed, not human-authored decisions. Raw response JSON remains the
authority for quote byte identities, not for external factual truth.
"""
from __future__ import annotations
import hashlib,json,os
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'forecast-seed-packets-20261029-v2'
SUMMARY=ROOT/'forecast-source-seed-20261029-01/summary.json'

def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def put(path,raw):
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 d=os.open(path.parent,os.O_RDONLY)
 try:os.fsync(d)
 finally:os.close(d)
def follow(x,parts):
 for part in parts:x=x[int(part)] if isinstance(x,list) else x[part]
 return x

def build():
 summary_raw=SUMMARY.read_bytes();summary=json.loads(summary_raw)
 if summary.get('status')!='completed' or summary.get('failure') is not None:raise ValueError('source phase incomplete')
 recs={x['id']:x for x in summary['settled_records']}
 if len(recs)!=4:raise ValueError('unexpected source cohort')
 development='Anthropic is officially valued at $1,000,000,000,000 ($1 Trillion) or more in a primary funding round or at its initial public offering (IPO) by December 31, 2026, according to SEC filings or major financial press.'
 accepted=ROOT/'dataset-draft-20261029/assembled-v3/human/case-02-decision-line.json'
 accepted_raw=accepted.read_bytes()
 if sha(accepted_raw)!='8b370f86d1c12dc9e59c60392825403c044c861b298b9a1e8b909bfa2a1973f8':raise ValueError('prior approval changed')
 old_manifest=json.loads((ROOT/'dataset-draft-20261029/assembled-v3/manifest.json').read_bytes())
 oldrow=next(x for x in old_manifest['cases'] if x['case_id']=='case-02')
 old_raw=(ROOT/'dataset-draft-20261029/assembled-v3'/oldrow['input_path']).read_bytes()
 if sha(old_raw)!=oldrow['input_sha256']:raise ValueError('prior proposal drift')
 oldcase=json.loads(old_raw)
 if next(x['text'] for x in oldcase['task']['initial_evidence'] if x['id']=='thesis')!=development:raise ValueError('prior accepted wording drift')
 cases=[
  {'case_id':'case-01','split':'development','thought':{'text':development,'origin':'prior_user_approved','human_confirmed':True,
   'acceptance_path':str(accepted.relative_to(ROOT)),'acceptance_sha256':sha(accepted_raw),
   'qualification':'Prior approval of this exact thesis; no new human decision or new fit review is implied.'},
   'op':'seed-anthropic-search','selections':[
    ('anthropic-search-1',['data','organic','1','snippet'],'Anthropic raises $65B in latest funding round at $965B valuation.',['data','organic','1','link'],['data','organic','1','date'],'search_snippet_unverified'),
    ('anthropic-search-2',['data','organic','5','snippet'],'Anthropic files S-1 with the SEC for proposed initial public offering',['data','organic','5','link'],None,'search_snippet_attributed_to_official_url_not_fetched')],
   'missing':['IPO price and final valuation not established by these snippets','Underlying pages and SEC filing not independently fetched in this phase']},
  {'case_id':'case-02','split':'diagnostic','thought':{'text':'Как данные об инфляции CPI и PCE могут повлиять на решение ФРС о процентной ставке до конца 2026 года?',
   'origin':'assistant_proposal_unaccepted','human_confirmed':False,'qualification':'A proposed exploratory question within the approved topic, not a statement of the user.'},
   'op':'seed-macro-news','selections':[
    ('macro-search-1',['data','news','0','snippet'],'Inflation, as measured by the PCE Price Index, is expected to have accelerated in September as oil and fuel prices surged.',['data','news','0','link'],['data','news','0','date'],'search_snippet_expectation_not_verified_fact'),
    ('macro-search-2',['data','news','4','snippet'],'The current U.S. inflation rate is 3.7%. The CPI rose 0.6% from August to September.',['data','news','4','link'],['data','news','4','date'],'search_snippet_unverified')],
   'missing':['Exact publication times and underlying source pages are not verified','Reported headline statistic must not be treated as the model-established ground truth']},
  {'case_id':'case-03','split':'diagnostic','thought':{'text':'Какие новые релизы моделей OpenAI могут быть объявлены до конца ноября 2026 года и какие связанные факторы стоит проверить?',
   'origin':'assistant_proposal_unaccepted','human_confirmed':False,'qualification':'A proposed exploratory question within the approved topic, not a statement of the user.'},
   'op':'seed-openai-search','selections':[],
   'missing':['The captured search did not provide sufficiently relevant official material on the requested model release plans','Further source discovery required; an empty selected packet is not proof that no such information exists']},
  {'case_id':'case-04','split':'diagnostic','thought':{'text':'Как решения OPEC+ о добыче нефти могут повлиять на цену WTI до конца 2026 года?',
   'origin':'assistant_proposal_unaccepted','human_confirmed':False,'qualification':'A proposed exploratory question within the approved topic, not a statement of the user.'},
   'op':'seed-opec-fetch','selections':[
    ('opec-fetch-1',['data','markdown'],'The seven OPEC+ countries, which previously announced additional voluntary adjustments in April and November 2023, namely Saudi Arabia, Russia, Iraq, Kuwait, Kazakhstan, Algeria, and Oman met virtually on 4 October 2026, to review global market conditions and outlook.',None,None,'retrieved_official_page_as_provider_extraction'),
    ('opec-fetch-2',['data','markdown'],'The seven participating countries decided to maintain September 2026 required production for November 2026 as detailed in the table below.',None,None,'retrieved_official_page_as_provider_extraction')],
   'missing':['This source does not establish a WTI price or the effect of OPEC+ production policy on that price','Exact source publication time not established']},
 ]
 OUT.mkdir(mode=0o700)
 manifest={'schema':'forecast-seed-packets-v1','supersedes_manifest_sha256':'6dc921e51deddfbfd65c1a6de16509058552fe2dee3a37aed677973478f7df9f','source_summary_path':str(SUMMARY.relative_to(ROOT)),
  'source_summary_sha256':sha(summary_raw),'cases':[],
  'review_status':'operator projection; not a human semantic adjudication or a blind holdout',
  'selection_rule':'curated topic-relevant literal excerpts; raw search listings are not primary-document verification'}
 for c in cases:
  op=c['op'];rec=recs[op];raw_path=ROOT/'forecast-source-seed-20261029-01'/(op+'.raw.json');raw=raw_path.read_bytes()
  if sha(raw)!=rec['response_sha256'] or rec['state']!='succeeded' or rec['http_status']!=200:raise ValueError('receipt mismatch')
  response=json.loads(raw)
  if response.get('success') is not True:raise ValueError('source failed')
  evidence=[]
  for ident,parts,quote,urlparts,dateparts,status in c['selections']:
   value=follow(response,parts)
   if quote not in value:raise ValueError('quote not present in source field')
   qb=quote.encode('utf-8');offset=raw.find(qb)
   if offset<0 or raw.count(qb)!=1 or raw[offset:offset+len(qb)].decode('utf-8')!=quote:raise ValueError('quote bytes missing or ambiguous')
   url=follow(response,urlparts) if urlparts else 'https://www.opec.org/pr-detail/616-4-october-2026.html'
   evidence.append({'id':ident,'text':quote,'source_url':url,'source_type':status,'json_pointer':'/'+'/'.join(parts),
    'raw_sha256':sha(raw),'source_effect_id':op,'byte_offset':offset,'byte_length':len(qb),
    'captured_at_utc':rec['completed_at_utc'],'available_at_observed_utc':rec['completed_at_utc'],
    'published_at_utc':None,'reported_date_literal':follow(response,dateparts) if dateparts else None,
    'validation_status':'literal raw response substring; external factual correctness not independently verified'})
  card={'schema':'forecast-seed-case-v1','case_id':c['case_id'],'split':c['split'],'thought':c['thought'],
   'evidence':evidence,'missing':c['missing'],'limitations':['No prediction-market titles or contract IDs included.',
   'The packet contains source-attributed claims, not independent verification.','Diagnostic use is exploratory, not a blind holdout.']}
  card_raw=canonical(card);path=OUT/(c['case_id']+'.json');put(path,card_raw)
  manifest['cases'].append({'case_id':c['case_id'],'split':c['split'],'input_path':path.name,'input_sha256':sha(card_raw),
   'source_effect_id':op,'raw_path':str(raw_path.relative_to(ROOT)),'raw_sha256':sha(raw),'evidence_count':len(evidence)})
 put(OUT/'manifest.json',canonical(manifest))
 return manifest

if __name__=='__main__':
 result=build()
 print(json.dumps({'manifest_sha256':sha((OUT/'manifest.json').read_bytes()),'cases':[(x['case_id'],x['evidence_count']) for x in result['cases']]},ensure_ascii=False))
