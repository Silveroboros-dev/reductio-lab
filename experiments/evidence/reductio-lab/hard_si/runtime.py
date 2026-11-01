"""Bounded Gemini adapter and successor ledger; no external effect at import."""
from __future__ import annotations
import json
from reasoning_engine.vertex_adapter import (build_generation_request,build_count_request,canonical_json,
 parse_vertex_response,model_matches,AdapterError,IncompleteGeneration)
from research.retry_facade import ledger_class

def generation_request(role_request,level):
 if level not in ('LOW','MEDIUM'):raise ValueError('thinking level denied')
 r=build_generation_request(role_request)
 r['generationConfig']['thinkingConfig']['thinkingLevel']=level
 return r

class Adapter:
 def __init__(self,facade,transport):self.facade,self.transport=facade,transport
 def complete(self,role_request,operation_id,level):
  request=generation_request(role_request,level);frozen=canonical_json(request)
  count_id='count:'+operation_id;generation_id='generation:'+operation_id
  self.facade.count(count_id,build_count_request(request),self.transport)
  raw=self.facade.generate(generation_id,json.loads(frozen),count_id,self.transport)
  result=parse_vertex_response(raw)
  if not model_matches(result.model_version):raise AdapterError('observed model mismatch')
  if result.finish_reason!='STOP':raise IncompleteGeneration(result.finish_reason,result)
  return result

def ledger_type(retry,contract):
 inherited=ledger_class(retry,contract)
 class Bound(inherited):
  @staticmethod
  def _validate_contract(c):
   if c!=contract:raise ValueError('contract mismatch')
   if (c['model'],c['location'],c['cap_micro'],c['max_generations'],c['max_counts'])!=('gemini-3.8-flash','global',60000000,1910,1834):
    raise ValueError('provider or budget cap mismatch')
 return Bound
