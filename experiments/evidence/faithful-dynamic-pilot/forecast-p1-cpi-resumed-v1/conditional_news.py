"""Conditional BEA release timing adapter: no source call or default verifier.

The BEA embargo time is a source-reported release time, used only under the
explicit assumption of an honored embargo; actual earliest visibility unknown.
"""
import copy,json
from pathlib import Path
import gate
ROOT=Path(__file__).resolve().parent.parent
AMENDMENT='forecast-cpi-p1-conditional-release-amendment-20261029-v1.json'
AMENDMENT_SHA='9ae7785ab87bf5619df206be7f8142680b51db405b12886227ac072458797798'
OBS='bea-september-pce-official-observation-20261029-v1.json'
OBS_SHA='437c09cdbec1606569b4b642cb8fc0bc54bea9dad9e1e1331a49d859b79fa274'
URL='https://www.bea.gov/news/2026/personal-income-and-outlays-september-2026'
class Error(ValueError):pass

def make(*,raw,receipt,verify_amendment,verify_fetch):
 """Return only receipt-bound news, with an explicit timing caveat in text.

 verify_amendment must independently review amendment bytes. verify_fetch
 must independently bind exact returned content, official source/URL, receipt,
 and values to the BEA observed page, not just trust a search result snippet.
 """
 if not callable(verify_amendment) or not callable(verify_fetch):raise Error('independent verifiers required')
 amendment=(ROOT/AMENDMENT).read_bytes();obsraw=(ROOT/OBS).read_bytes()
 if gate.sha(amendment)!=AMENDMENT_SHA or gate.sha(obsraw)!=OBS_SHA or verify_amendment(amendment) is not True:raise Error('conditional amendment unreviewed or changed')
 a=json.loads(amendment);obs=json.loads(obsraw)
 if a['observation_sha256']!=OBS_SHA or a['gate_sha256']!=gate.sha((Path(__file__).parent/'gate.py').read_bytes()) or obs['official_url']!=URL or obs['actual_first_publication_time_utc'] is not None or a['stated_embargo_release_utc']!=obs['scheduled_embargo_release_utc']:raise Error('observation binding invalid')
 if not isinstance(raw,bytes) or not isinstance(receipt,dict) or receipt.get('id')!='p1-cpi-bea-fetch' or receipt.get('kind')!='source' or receipt.get('state')!='succeeded' or receipt.get('http_status')!=200 or receipt.get('response_hash')!=gate.sha(raw) or bytes(receipt.get('response',b''))!=raw or type(receipt.get('actual_micro')) is not int or receipt['actual_micro']<0:raise Error('source receipt invalid')
 try:
  published=gate.o.instant(a['stated_embargo_release_utc']);available=gate.o.instant(obs['observed_at_utc']);captured=gate.o.instant(receipt['completed_at_utc'])
  if not gate.o.instant(gate.DURABLE)<published<=available<=captured:raise Error('source time ordering invalid')
 except (KeyError,gate.o.EligibilityError):raise Error('source time missing') from None
 if verify_fetch(raw,copy.deepcopy(receipt),copy.deepcopy(obs)) is not True:raise Error('official BEA source content unverified')
 v=obs['values']
 text=('BEA Personal Income and Outlays, September 2026: PCE price index '+str(v['pce_monthly_percent'])+'% month over month and '+str(v['pce_yearly_percent'])+'% year over year; excluding food and energy '+str(v['core_pce_monthly_percent'])+'% month over month and '+str(v['core_pce_yearly_percent'])+'% year over year. '
  'The published_at_utc field is a conditional proxy for BEA stated release at 12:30 UTC on October 29, assuming the embargo was respected. The first actual public visibility was not independently measured. September PCE and October CPI are different measures.')
 return [{'id':'news:bea-pce-september-2026-conditional','kind':'news','text':text,'source':URL,
  'published_at_utc':a['stated_embargo_release_utc'],'available_at_utc':obs['observed_at_utc'],'captured_at_utc':receipt['completed_at_utc']}]
