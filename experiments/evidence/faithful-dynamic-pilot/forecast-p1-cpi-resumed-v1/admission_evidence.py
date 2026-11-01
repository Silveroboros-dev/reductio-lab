"""Reconstruct the real CPI P1 admission and bind it to captured receipts.

A separate independent review is still necessary. No network or source calls.
"""
import copy,json
from pathlib import Path
import gate,conditional_capture,conditional_news,venue_capture,dispatch_frozen
ROOT=Path(__file__).resolve().parent.parent
PRE=ROOT/'forecast-cpi-p1-prefreeze-20261029-v1.json'
PRE_SHA='37bd8a3ac7d58d14f18bedabcccc36fd0ede879732ceda69819afcdd4afe431f'
DISPATCH=ROOT/'forecast-cpi-p1-dispatch-contract-20261029-v1.json'
DISPATCH_SHA='ae04990a3deae9cb4d8e9fa78948d2bc652ea668dac02f699312030af38b03e4'
class Error(ValueError):pass

def verify_news(news,t1):
 try:
  expected=conditional_capture.candidate(verify_amendment=lambda b:gate.sha(b)==conditional_news.AMENDMENT_SHA)
  return news==expected and gate.o.instant(news[0]['captured_at_utc'])<=gate.o.instant(t1)
 except Exception:return False

def inspect():
 raw=PRE.read_bytes();d=DISPATCH.read_bytes()
 if gate.sha(raw)!=PRE_SHA or gate.sha(d)!=DISPATCH_SHA:raise Error('prefreeze or dispatch digest mismatch')
 pre=json.loads(raw);contract=json.loads(d)
 if gate.canonical(pre)!=raw or gate.canonical(contract)!=d or dispatch_frozen.expected(pre)!=contract or gate.sha(dispatch_frozen.GATEWAY_AMENDMENT.read_bytes())!=dispatch_frozen.GATEWAY_AMENDMENT_SHA:raise Error('dispatch scope drift')
 source=json.loads(conditional_capture.CONTRACT.read_bytes())
 if gate.sha(conditional_capture.CONTRACT.read_bytes())!=conditional_capture.SOURCE_CONTRACT_SHA:raise Error('source contract drift')
 if pre['remaining_status_operations']!=[x for x in source['operations'] if x['kind']=='status_refresh' and x['ticket']['id']!='p1-cpi-status-01']:raise Error('status operation drift')
 admission=gate.prepare(copy.deepcopy(pre['news']),copy.deepcopy(pre['initial_status']),t1=pre['t1'],verify_news=verify_news,verify_status=venue_capture.verify_status)
 if admission!=pre['admission'] or admission.get('status')!='ready':raise Error('admission cannot be replayed from actual evidence')
 return pre

def verify_admission(admission):
 try:return inspect()['admission']==admission
 except Exception:return False
