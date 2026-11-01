"""Bind model stage scope to the latest independently verified venue receipt.

This guard checks local freshness; the injected verifier must establish actual
upstream authenticity and absence of stale cache. No provider effects here.
"""
import copy
import gate
class Guard:
 def __init__(self,*,account,clock,verify_status):
  if not callable(clock) or not callable(verify_status):raise ValueError('clock and provenance verifier required')
  self.account=account;self.clock=clock;self.verifier=verify_status;self.current=None
  self.case=gate.verify_p0()['prepared']['case']
 def _valid(self,status,case,at):
  if not isinstance(status,dict) or case!=self.case or status.get('contract_id')!=gate.TICKER or status.get('state')!='active' or status.get('result')!='' or status.get('rules_primary')!=case.get('rules_primary') or status.get('rules_secondary')!=case.get('rules_secondary'):return False
  try:
   now=gate.o.instant(at);obs=gate.o.instant(status['observed_at_utc']);capt=gate.o.instant(status['captured_at_utc']);close=gate.o.instant(case['close_time_utc'])
  except (KeyError,gate.o.EligibilityError):return False
  return obs<=capt<=now<close and 0<=(now-capt).total_seconds()<=300
 def verify_status(self,status,case,at):
  if not self._valid(status,case,at) or self.verifier(copy.deepcopy(status),copy.deepcopy(case),at) is not True:return False
  if self.current is not None and gate.o.instant(status['captured_at_utc'])<gate.o.instant(self.current['captured_at_utc']):return False
  self.current=copy.deepcopy(status);return True
 def verify_scope(self):
  if self.current is None or not self._valid(self.current,self.case,self.clock()):return False
  try:
   if self.account.verify() is not None:return False
   summary=self.account.summary()
   return (summary.get('stopped')==0 and type(summary.get('source_attempts')) is int and summary['source_attempts']<=28
    and self._valid(self.current,self.case,self.clock()))
  except Exception:return False
