"""No-retry p0 model adapter with time between ALL provider calls."""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for d in ('forecast-controller-v1','forecast-stopped-successor-v1'):
 sys.path.insert(0,str(ROOT/d))
import forecast,recovery

class Error(ValueError):pass
class Pacer:
 def __init__(self,interval=20,*,monotonic=time.monotonic,sleep=time.sleep):
  if type(interval) not in (int,float) or interval<20 or interval>60:raise Error('interval out of range')
  self.interval=interval;self.monotonic=monotonic;self.sleep=sleep
  # Even the first call waits; this does not assume a known retry-after.
  self.last_end=self.monotonic()
 def wait(self,scope):
  if scope() is not True:raise Error('scope invalid before pacing')
  while True:
   remaining=self.last_end+self.interval-self.monotonic()
   if remaining<=0:break
   self.sleep(min(remaining,20.0))
  if scope() is not True:raise Error('scope invalid after pacing')
 def ended(self):self.last_end=self.monotonic()

def factory(ledger,*,case_ids,transport,verify_scope,pacer):
 if not isinstance(ledger,recovery.ModelOnlyLedger):raise Error('reviewed model-only ledger required')
 if tuple(case_ids)!=('case-03','case-04') or not callable(transport) or not callable(verify_scope) or not isinstance(pacer,Pacer):raise Error('scope mismatch')
 started=set()
 def guard(provider,endpoint,body):
  if provider!='vertex' or endpoint not in ('countTokens','gemini-3.8-flash@global') or verify_scope() is not True:
   ledger.stop('paced p0 scope drift');raise Error('forbidden provider or scope')
  return transport(provider,endpoint,body)
 def make(case_id,phase,condition,arm):
  key=(case_id,arm)
  if case_id not in case_ids or (phase,condition)!=('p0','no_news') or arm not in ('c','b') or key in started:raise Error('case, arm, or retry prohibited')
  started.add(key);n=0
  def generate(stage,payload):
   nonlocal n
   if n>=23:raise Error('per-arm generation cap')
   n+=1;ident=f'p0:{case_id}:{arm}:{n:02d}';request=forecast.build_request(stage,payload)
   # Wait outside ledger.count/generate: no effect is in started state during
   # sleep. Timestamp after each returns, even on error, so a caller cannot
   # shorten the spacing with a slow or failed provider call.
   pacer.wait(verify_scope)
   try:ledger.count('count:'+ident,request,guard)
   finally:pacer.ended()
   pacer.wait(verify_scope)
   try:raw=ledger.generate('generation:'+ident,request,'count:'+ident,guard)
   finally:pacer.ended()
   return forecast.parse_response(json.loads(raw))
  return generate
 return make
