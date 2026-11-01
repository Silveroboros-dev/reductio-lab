"""Staged, fully injected composition for one CPI P1 continuation.

No default provider, endpoint, news, credentials, ledger activation, telemetry
or authority. The caller must freeze and challenge the exact event and status
operations and pass separately activated stages sharing one current ledger.
"""
from __future__ import annotations
import copy
import gate,runner,stages
class Error(ValueError):pass

def run(*,news,initial_status,t1,model_stage,source_stage,status_operations,model_transport,
        source_transport,decode_status,verify_operation,verify_news,verify_status,
        verify_admission,verify_ledger,record,clock,pacer):
 """P1 only: no source/model effect until independently verified admission.

 `verify_news`, `verify_status`, `verify_admission`, and `verify_operation`
 must independently bind exact immutable source bytes, event first publication,
 same open venue rules, reviewed scope and authorized operations. Their mere
 presence or a mock returning True does not establish any of those facts.
 `record` must be create-only and durable; model/source stage implementations
 own no-retry attempts, cost accounting and capture before return.
 """
 inputs=gate.prepare(copy.deepcopy(news),copy.deepcopy(initial_status),t1=t1,
  verify_news=verify_news,verify_status=verify_status,max_status_age_seconds=300)
 if inputs.get('status')!='ready':return inputs
 if not callable(verify_admission) or verify_admission(copy.deepcopy(inputs)) is not True:raise Error('frozen admission review required')
 facade=stages.ModelFacade(model_stage,source_stage)
 refresh=stages.status_refresher(source_stage,copy.deepcopy(status_operations),transport=source_transport,decode=decode_status,
  verify_operation=verify_operation,record=record)
 return runner.run(inputs,copy.deepcopy(initial_status),ledger=facade,transport=model_transport,
  refresh_status=refresh,verify_status=verify_status,verify_admission=verify_admission,
  verify_ledger=verify_ledger,record=record,clock=clock,pacer=pacer)
