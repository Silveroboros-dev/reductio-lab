"""Offline, create-only draft. No provider calls and no governed writes."""
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
OUTPUT=Path(__file__).resolve().parent
WORKTREE=Path('/Users/rk/.codex/worktrees/controller-evidence-integration/fitcheck-core')
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return p.read_bytes()
def write(name, data):
 raw=(json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
 with (OUTPUT/name).open('xb') as f:f.write(raw)
 return sha(raw)

market_path=ROOT/'kalshi_preflight/user_supplied_targeted_kalshi_markets.json'
market_raw=read(market_path); market_sha=sha(market_raw)
assert market_sha=='2f6932c840ecbfc4bc3dac1f52a4f27aeac250f66fe345d0ad371c50be57363b'
markets=json.loads(market_raw)['markets']; by_id={m['ticker']:m for m in markets}
assert len(markets)==len(by_id)==8 and len({m['event_ticker'] for m in markets})==8
accept_path=ROOT/'kalshi_preflight/human_test_theses_acceptance.json'
accept_raw=read(accept_path); accept=json.loads(accept_raw)
assert accept['user_response']=='Да, принимаю все шесть' and len(accept['test_theses_ru'])==6
receipt_path=ROOT/'kalshi_preflight/user_reported_targeted_capture.json'
receipt_raw=read(receipt_path); receipt=json.loads(receipt_raw)
assert receipt['content_sha256']==market_sha and receipt['reported_http_status']==200
review_path=WORKTREE/'data/review/review_packets_v0.jsonl'
review_raw=read(review_path)
decisions_path=WORKTREE/'data/review/normalization_holdout_20260827_v1/source_initial_human_decisions_v1.jsonl'
decisions_raw=read(decisions_path)
packets={}
for rawline in review_raw.splitlines():
 item=json.loads(rawline)
 packets[item['packet_id']]=(item,sha(rawline))
packet_ids=[
'pkt_mfta_governance_50_gov_027_eval-v2-013__normrepair_holdout-20260827-v1-exact-approvals-v1',
'pkt_mfta_governance_50_gov_004_eval-007__normrepair_holdout-20260827-v1-exact-approvals-v1__livefill_holdout-20260827-v1-case03-anthropic-1t-followup-v1']
decisions={}
for rawline in decisions_raw.splitlines():
 d=json.loads(rawline)
 if d.get('status')=='approved_exact_proposal' and d.get('final_verdict')=='approve': decisions[d.get('proposal_digest')]=(d,sha(rawline))
dev=[]
for packet_id in packet_ids:
 p,line_hash=packets[packet_id]; prov=p['source_provenance']; decision,decision_hash=decisions[prov['normalization_repair_proposal_digest']]
 dev.append({'original_text':p['normalized_claim']['contractible_version'],'language':'en','authority_scope':'historical advisory normalization approval only; no new human thesis acceptance and no pair label transfer',
  'provenance':{'packet_id':packet_id,'packet_source_path':str(review_path),'packet_file_sha256':sha(review_raw),'packet_original_line_sha256':line_hash,
    'approval_source_path':str(decisions_path),'approval_file_sha256':sha(decisions_raw),'approval_original_line_sha256':decision_hash,
    'case_ordinal':decision['case_ordinal'],'proposal_digest':decision['proposal_digest'],'status':decision['status'],'final_verdict':decision['final_verdict'],
    'recorded_at_utc':decision['recorded_at_utc']}})

tickers=['KXFEDDECISION-26DEC-H25','KXIPO-26-ANTHROPIC','KXHIGHINFLATION-26DEC-T4.2','KXUSGDPSHARE-27JUL01-T25.7','KXANTHROPICRESCIND-26JUN-27JAN01','KXCLAUDE-CLAUDE6-26DEC31','KXGDPNOM-US26-32.8','KXRSIANNOUNCE-29-27JAN01']
queries=[
 ('Federal Reserve interest rate decisions 2026 2027 latest target range changes','Whether any officially reported cut or policy event has occurred in the relevant window; cannot establish future no-cut proposition or rewrite the contract.'),
 ('Anthropic funding round valuation IPO announcement 2026 latest','Whether a primary funding round or IPO valuation has been reported and with what date/source; IPO announcement alone does not establish $1T.'),
 ('2026 consumer price index year over year inflation reports 4.2 percent official','Whether any relevant year-over-year CPI report already exceeded 4.2%; a partial year cannot establish future absence.'),
 ('World Bank 2026 United States world GDP current US dollars WDI latest revision','Whether a 2026 first or revised WDI estimate is published and which version it is; absence or a forecast is not a final revision.'),
 ('Anthropic supply chain risk designation rescinded waiver modification White House Department of Defense 2026','Whether a documented official action fully rescinds the designation or only waives/modifies it; a headline alone may not establish scope.'),
 ('Anthropic Claude 6 release publicly available free tier official 2026','Whether an official release occurred, whether it is public and whether free users can access it; announcements and beta do not settle each condition.'),
 ('BEA 2026 annual nominal GDP first nonpreliminary estimate World Bank GDP release','Whether BEA and World Bank official annual data and their versions are available; avoid equating forecasts, preliminary data and distinct sources.'),
 ('OpenAI Anthropic recursive self improvement independent verification public demonstration 2026','Whether there is a dated official announcement, a public demonstration and genuinely independent verification; these conditions are distinct.')]
guide_path=WORKTREE/'docs/label_guide.md'; guide_raw=read(guide_path); guide_sha=sha(guide_raw)
labels=['direct','indirect','weak_proxy','not_an_expression','unknown']
assert set(tickers)==set(by_id)
created=dt.datetime.now(dt.timezone.utc).isoformat()
groups=[]
for i,ticker in enumerate(tickers):
 m=by_id[ticker]; ident=f'case-{i+1:02d}'
 if i<2: thesis=dev[i]
 else: thesis={'original_text':accept['test_theses_ru'][i-2],'language':'ru','authority_scope':accept['scope'],
  'provenance':{'acceptance_source_path':str(accept_path),'acceptance_sha256':sha(accept_raw),'test_thesis_index':i-2,'user_message_id':'01a186e5-7149-7d53-b414-6b39d81a0e2c','accepted_text':accept['user_response'],'recorded_at_utc':accept['recorded_at_utc']}}
 assert m['event_ticker'] and m['ticker']==ticker and m['rules_primary']
 initial=[{'id':'thesis','text':thesis['original_text'],'source':'human-confirmed-wording' if i>=2 else 'historical-normalization-approval'},
          {'id':'market-id','text':ticker,'content_sha256':market_sha},
          {'id':'market-title','text':m['title'],'content_sha256':market_sha},
          {'id':'label-guide','text':guide_raw.decode(),'content_sha256':guide_sha}]
 replay=[{'id':'primary-rule','text':m['rules_primary'],'content_sha256':market_sha,'source_field':'rules_primary'}]
 if m.get('rules_secondary'):
  replay.append({'id':'secondary-rule','text':m['rules_secondary'],'content_sha256':market_sha,'source_field':'rules_secondary'})
 conflict=[]
 if ticker=='KXFEDDECISION-26DEC-H25':conflict=[{'contract_id':ticker,'field':'rules_secondary','status':'unresolved','description':'API payload omits > in example while public indexed Kalshi page shows >25; verification response repeats API text. Origin/cause unresolved; no silent repair.'}]
 q,gap=queries[i]
 groups.append({'case_id':ident,'split':'dev' if i<2 else 'test_candidate','event_group_id':m['event_ticker'],'contract_ids':[ticker],
 'thesis':thesis,'question':'Assess how well the market contract expresses the human thesis using the visible evidence and active pair-label guide. If essential evidence is missing, use unknown.',
 'allowed_labels':labels,'initial_evidence':initial,
 'manual_rule_capture':{'action_id':'manual-rules','capture_kind':'manual_capture','quoted_cost_micro_usd':None,'expected_cost_status':'unknown',
   'description':'Read this market\'s stored primary and secondary rule fields as available in the user-relayed Kalshi response.',
   'source_path':str(market_path),'source_sha256':market_sha,'receipt_path':str(receipt_path),'receipt_sha256':sha(receipt_raw),
   'reported_request_start_utc':receipt['reported_request_start_utc'],'reported_request_end_utc':receipt['reported_request_end_utc'],
   'origin_assurance':'user-relayed Grok report; independent provider transport not verified',
   'replay_evidence':replay,'secondary_field_empty':not bool(m.get('rules_secondary')),'completeness':'not established'},
 'news_action_draft':{'action_id':'news','capture_kind':'paid_api','provider':'orthogonal','api':'serper','endpoint':'/news',
   'request_body':{'q':q,'num':3},'predeclared_relevance_gap':gap,'query_fixed_at_utc':created,
   'quoted_cost_micro_usd':None,'quote_status':'not obtained','response':None,'response_status':'not captured'},
 'source_conflicts':conflict})
assert [g['thesis']['original_text'] for g in groups[2:]]==accept['test_theses_ru']
assert len({g['event_group_id'] for g in groups})==8
manifest={'schema':'faithful-dynamic-draft-v1','status':'draft_not_frozen_not_runnable',
 'created_at_utc':created,'user_confirmation_scope':'six test wording strings only; not truth, review labels, goldens or product policy',
 'event_counts':{'development_exposed':2,'diagnostic_test_candidates':6},
 'user_relayed_source':{'path':str(market_path),'sha256':market_sha,'bytes':len(market_raw),'receipt_path':str(receipt_path),'receipt_sha256':sha(receipt_raw)},
 'label_guide':{'path':str(guide_path),'sha256':guide_sha},
 'limitations':['No Orthogonal source response or price has been invented.','No model/provider call has been run.','This draft is not the runnable manifest; source capture, account price and cohort review remain pending.','All eight are single-contract cases; pool-level/top-three cannot be evaluated.','Human acceptance of wordings is not human semantic adjudication.','Prior dev normalization approvals were scoped advisory and do not automatically attest a new session.','Source transport provenance is user-relayed, not independently verified.','Fresh news may not change fit for fixed complete thesis and rules.'],
 'groups':groups}
print('draft_sha256',write('draft.json',manifest),'groups',len(groups),'source_sha256',market_sha)
