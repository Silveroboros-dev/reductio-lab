"""Injected adapter for the separately reviewed original P0 resume ledger.

No credentials, HTTP client, run authorization or effects are supplied here.
Only a live dispatcher reviewed separately may instantiate a real transport.
"""
import copy
import resume

class Error(ValueError):pass

def generator(ledger,transport,verify_binding):
 if not all(callable(getattr(ledger,x,None)) for x in ('retry_failed','count_new','generate_new')) or not callable(transport) or not callable(verify_binding):raise Error('missing callbacks')
 def call(binding,stage,request):
  if not isinstance(binding,dict) or not isinstance(request,dict) or resume.sha(resume.canonical(request))!=binding.get('request_sha256'):raise Error('request binding mismatch')
  if verify_binding(copy.deepcopy(binding),stage,copy.deepcopy(request)) is not True:raise Error('reviewed binding rejected')
  case=binding.get('case_id');arm=binding.get('arm');n=binding.get('ordinal')
  if case not in resume.CONFIG or arm not in ('b','c') or type(n) is not int or not 1<=n<=23:raise Error('invalid scope')
  logical=f'p0:{case}:{arm}:{n:02d}'
  if binding.get('kind')=='retry_confirmed_429':
   if binding.get('predecessor_generation_id')!='generation:'+logical:raise Error('wrong failed identity')
   return ledger.retry_failed(binding['predecessor_generation_id'],request,transport)
  if binding.get('kind')!='unattempted':raise Error('unknown operation kind')
  ledger.count_new(logical,request,transport)
  return ledger.generate_new(logical,request,transport)
 return call
