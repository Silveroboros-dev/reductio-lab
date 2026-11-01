"""CPI P1 preflight after a verified event, before frozen model activation.

No built-in transport, credentials, clock or verification. A paid source effect
is possible only through an independently activated source stage and an exact
one-shot approved operation. Do not call this while data or review are absent.
"""
import copy
import gate,stages

class Error(ValueError):pass

def prepare(*,news,source_stage,status_operations,source_transport,decode_status,
            verify_operation,verify_news,verify_status,verify_source_stage,record,clock):
 """Verify new event; take one status observation; prepare four frozen arms.

 The source stage has an exact allowlist and all source effects share the same
 cumulative 28-call ledger. At least one separate status ticket remains for a
 final post-result observation. This function does not activate a model or
 establish source authenticity; reviewer callbacks must bind real receipts.
 """
 if not all(callable(x) for x in (source_transport,decode_status,verify_operation,verify_news,verify_status,verify_source_stage,record,clock)):raise Error('callbacks required')
 if not news:return gate.pending('no_eligible_new_event')
 now=clock()
 checked=gate.verify_p0()
 try:
  if not gate.o.instant(gate.DURABLE)<gate.o.instant(now)<gate.o.instant(checked['prepared']['case']['close_time_utc']):return gate.pending('t1_outside_open_interval')
 except (KeyError,gate.o.EligibilityError):return gate.pending('invalid_t1_or_case_time')
 if verify_news(copy.deepcopy(news),now) is not True:return gate.pending('news_provenance_or_semantic_novelty_unconfirmed')
 try:
  if not isinstance(news,list) or any(not isinstance(e,dict) or e.get('kind')!='news' or not gate.o.instant(gate.DURABLE)<gate.o.instant(e['published_at_utc'])<=gate.o.instant(e['available_at_utc'])<=gate.o.instant(e['captured_at_utc'])<=gate.o.instant(now) for e in news):return gate.pending('news_not_provably_after_durable_p0')
 except (KeyError,TypeError,gate.o.EligibilityError):return gate.pending('news_timestamp_missing')
 if not isinstance(status_operations,list) or len(status_operations)<2 or len(status_operations)>9:raise Error('need initial and final separate bounded observations')
 account=getattr(source_stage,'account',None)
 if account is None or verify_source_stage(source_stage) is not True:raise Error('verified source stage required')
 before=account.summary();remaining=28-before.get('source_attempts',28)
 if before.get('stopped')!=0 or remaining<2 or len(status_operations)>remaining:raise Error('source attempts unavailable')
 # Constructor validates every ticket/ID and performs no effects.
 refresh=stages.status_refresher(source_stage,copy.deepcopy(status_operations),transport=source_transport,decode=decode_status,verify_operation=verify_operation,record=record)
 status=refresh()
 if account.summary().get('source_attempts')!=before['source_attempts']+1:raise Error('initial status not recorded in shared ledger')
 t1=clock()
 admission=gate.prepare(copy.deepcopy(news),copy.deepcopy(status),t1=t1,verify_news=verify_news,verify_status=verify_status,max_status_age_seconds=300)
 if admission.get('status')!='ready':return admission
 return {'schema':'cpi-p1-prefreeze-v1','news':copy.deepcopy(news),'initial_status':status,'t1':t1,
         'admission':admission,'remaining_status_operations':copy.deepcopy(status_operations[1:]),
         'qualification':'Requires independent freeze and challenge before model activation; no claim that proxy receipt proves upstream freshness.'}
