"""Build p0 candidate records from a specific human decision and user relay.

No network and no writes. The verifier is a required independent review of the
human-origin record and attributable source/semantic match; relayed source is
not a direct API capture and model proposals never acquire human authorship.
"""
import copy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-seed-launch-v1'))
import launcher as seed
import p0_launcher as p

APPROVAL='4f8f2eed555d341bd95bbae298ffb35d38bfe3c30b6448bf1c75de54383a25f6'
RAW='459f460e7da6d6fcd81d837652f0a487cbe70e7d317f7a29907b5f0eb877bdf1'
META='03084e1c5d4740b18082f4c963c70f408d13e866bb46de74820b139c4a717d53'
TICKERS=('KXIPO-26-ANTHROPIC','KXCPI-26OCT-T0.2','KXGPT-ASTRA61-26NOV13','KXWTI-26NOV03-T97.99')
GROUPS=('anthropic-valuation-ipo','us-inflation-october','openai-astra61-release','wti-november03')

class Error(ValueError):pass

def _read(name,expected):
 raw=p._read(ROOT/name)
 if p.o.sha(raw)!=expected:raise Error('bound input digest mismatch: '+name)
 return p._json(raw)

def build(as_of_utc,*,verify_human_origin,verify_relays_and_fit):
 """Return candidate case dictionaries, not create or approve files.

 verify_human_origin(decision) independently checks the genuine user response
 against the available chat record. verify_relays_and_fit(case, market, meta)
 checks relay provenance and evaluates expressiveness without claiming direct
 verification; it is mandatory for each case and may reject any mismatch.
 """
 decision=_read('human-test-question-acceptance-20261029-v1.json',APPROVAL)
 raw=_read('kalshi-user-relay-20261029-v1.raw.json',RAW)
 meta=_read('kalshi-user-relay-20261029-v1.provenance.json',META)
 origin=decision.get('decision_origin',{})
 if (decision.get('schema')!='human-test-question-acceptance-v1' or
  origin.get('kind')!='user_response_to_assistant_question' or origin.get('answer')!='Подходит как тестовый список' or
  origin.get('exact_response_time_utc') is not None or not isinstance(decision.get('questions_as_presented'),list) or len(decision['questions_as_presented'])!=4):raise Error('human decision binding mismatch')
 if (meta.get('schema')!='user-relayed-kalshi-capture-v1' or meta.get('raw_sha256')!=RAW or
  meta.get('origin',{}).get('kind')!='user_relay_of_grok_output' or meta.get('origin',{}).get('claims_independently_verified') is not False):raise Error('source relay attribution mismatch')
 if not callable(verify_human_origin) or verify_human_origin(copy.deepcopy(decision)) is not True:raise Error('human origin independently unverified')
 t=p.o.instant(as_of_utc)
 if p.o.instant(decision['recorded_at_utc'])>t or p.o.instant(meta['recorded_at_utc'])>t:raise Error('records postdate as-of')
 markets=raw.get('markets')
 if not isinstance(markets,list) or len(markets)!=4:raise Error('four-market relay required')
 byid={x.get('ticker'):x for x in markets if isinstance(x,dict)}
 if set(byid)!=set(TICKERS) or len(byid)!=len(markets):raise Error('ticker set mismatch')
 # This revalidates existing, source-attributed exact excerpts and their source
 # receipts; excludes any post-seed news or newly invented facts.
 projected=seed.tasks(as_of_utc)
 cases=[]
 for i,(ticker,group,row) in enumerate(zip(TICKERS,GROUPS,projected)):
  market=byid[ticker];thesis=decision['questions_as_presented'][i]
  if (not isinstance(thesis,str) or not thesis.strip() or market.get('status')!='active' or market.get('result')!='' or
   market.get('market_type')!='binary' or not isinstance(market.get('rules_primary'),str) or not market['rules_primary'].strip() or
   not isinstance(market.get('rules_secondary'),str) or p.o.instant(market['close_time'])<=t):raise Error('market snapshot ineligible')
  baseline=[]
  for e in row['task']['evidence']:
   z=copy.deepcopy(e);z['kind']='context';baseline.append(z)
  bid=market.get('yes_bid_dollars');ask=market.get('yes_ask_dollars')
  if not isinstance(bid,str) or not isinstance(ask,str):raise Error('market quote missing from relay')
  baseline.append({'id':'market:quote','kind':'market_quote',
   'text':'User-relayed market snapshot reports YES bid '+bid+' USD and YES ask '+ask+' USD; quote may be stale.',
   'source':'Grok response relayed by user; direct GET and underlying response bytes not independently verified; capture SHA-256 '+RAW,
   'available_at_utc':meta['recorded_at_utc'],'captured_at_utc':meta['recorded_at_utc']})
  c={'case_id':row['case_id'],'event_group_id':group,'thesis':thesis,'contract_id':ticker,
   'rules_primary':market['rules_primary'],'rules_secondary':market['rules_secondary'],
   'rules_capture_sha256':RAW,'rules_capture_source':'User-relayed Grok output; claimed direct GET and original network bytes not independently verified',
   'rules_captured_at_utc':meta['recorded_at_utc'],
   'close_time_utc':market['close_time'],'p0_as_of_utc':as_of_utc,'baseline_evidence':baseline,
   'human_approval':{'thesis_sha256':p.o.sha(thesis.encode()),'approval_recorded_at_utc':decision['recorded_at_utc']}}
  if not callable(verify_relays_and_fit) or verify_relays_and_fit(copy.deepcopy(c),copy.deepcopy(market),copy.deepcopy(meta)) is not True:
   raise Error('relayed rules or semantic fit unreviewed')
  cases.append(c)
 return cases
