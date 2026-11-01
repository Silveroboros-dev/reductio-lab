"""Fresh status guard with newly authorized cumulative source limit 38."""
import status_guard
class Guard(status_guard.Guard):
 def verify_scope(self):
  if self.current is None or not self._valid(self.current,self.case,self.clock()):return False
  try:
   if self.account.verify() is not None:return False
   s=self.account.summary()
   return s.get('stopped')==0 and type(s.get('source_attempts')) is int and s['source_attempts']<=38 and self._valid(self.current,self.case,self.clock())
  except Exception:return False
