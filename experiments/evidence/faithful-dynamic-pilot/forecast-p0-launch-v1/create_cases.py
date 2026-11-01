"""Create one candidate p0 case packet; no provider, ledger or model access.

Outputs require independent review; this script doesn't attest user identity,
validate an upstream HTTP response, or certify a semantic match.
"""
import datetime as dt,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-p0-launch-v1'))
import approved_inputs as a,p0_launcher as p

QUESTION_ID='["request_user_input_async","call_8f48381049684e4e9c4f747b75955376",0]'
ASSESSMENTS={
 'case-01':{'fit':'partial','details':'IPO confirmation can be Yes on an effective S-1, IPO pricing, or ticker assignment; no $1T valuation or primary financing threshold appears in rules. Forecast is P(YES of contract), not P(thesis).'},
 'case-02':{'fit':'provisional','details':'Rules specify October CPI increase above 0.2% at the single-decimal published value; ensure source agency/series meaning and frequency are understood, and do not infer any causal Fed outcome from the contract.'},
 'case-03':{'fit':'provisional','details':'Rules specify Astra 6.1 public release before Nov 13, outside closed beta, high-cost paid tier allowed; do not substitute Terra or another model.'},
 'case-04':{'fit':'provisional','details':'Rules specify Nov 3 front-month WTI settle above $97.99, not spot or OPEC compliance; expected_expiration_time is earlier than close_time, so independent unresolved verification is required.'},
}
def decision_check(d):
 o=d.get('decision_origin',{})
 return (o.get('question_item_id')==QUESTION_ID and o.get('answer')=='Подходит как тестовый список'
  and o.get('exact_response_time_utc') is None and 'предложен ассистентом' in d.get('qualifications',''))
def relay_check(c,m,meta):
 try:idx=int(c['case_id'][-2:])-1
 except (ValueError,KeyError):return False
 return (0<=idx<4 and c['contract_id']==a.TICKERS[idx] and m.get('ticker')==a.TICKERS[idx]
  and c['rules_primary']==m.get('rules_primary') and c['rules_secondary']==m.get('rules_secondary')
  and c['rules_capture_sha256']==a.RAW and meta.get('origin',{}).get('claims_independently_verified') is False)

def main():
 if Path.cwd().resolve()!=ROOT:raise ValueError('artifact root required')
 asof=dt.datetime.now(dt.timezone.utc).isoformat()
 cases=a.build(asof,verify_human_origin=decision_check,verify_relays_and_fit=relay_check)
 prepared=[p.o.prepare_case(c,verify_human=decision_check_case,verify_rules=rule_check_case) for c in cases]
 out=ROOT/'forecast-p0-cases-20261029-v2';record=p.durable_recorder(out)
 bindings=[]
 for c,pr in zip(cases,prepared):
  record(c['case_id'],c)
  path=out/(c['case_id']+'.json');raw=p._read(path)
  bindings.append({'case_id':c['case_id'],'path':str(path),'raw_sha256':p.o.sha(raw),
                   'case_sha256':pr['case_sha256'],'task_sha256':pr['task_sha256'],
                   'fit_assessment':ASSESSMENTS[c['case_id']]})
 manifest={'schema':'forecast-p0-case-candidates-v1','common_as_of_utc':asof,'case_bindings':bindings,
  'approval_sha256':a.APPROVAL,'market_relay_sha256':a.RAW,'market_provenance_sha256':a.META,
  'human_origin':'assistant_proposal_accepted; user response time unknown; recorded_at is upper bound',
  'market_origin':'user relayed Grok output; upstream HTTP and network bytes unverified',
  'supersedes_manifest_sha256':'306eda7041a4d1945e45a0888fa6b52bd430706cb709b483245499fdd50ee2aa',
  'status':'candidate_not_yet_independently_reviewed_or_authorized_for_dispatch'}
 record('manifest',manifest)
 print('common_as_of_utc:',asof)
 print('manifest_sha256:',p.o.sha(p._read(out/'manifest.json')))
 for b in bindings:print(b['case_id'],b['raw_sha256'],b['fit_assessment']['fit'])

def decision_check_case(case):
 return case.get('case_id') in ASSESSMENTS and 'approval_recorded_at_utc' in case.get('human_approval',{})
def rule_check_case(case):
 return case.get('contract_id') in a.TICKERS and case.get('rules_capture_sha256')==a.RAW
if __name__=='__main__':main()
