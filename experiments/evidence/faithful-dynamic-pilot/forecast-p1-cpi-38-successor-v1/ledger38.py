"""Candidate CPI P1 two-arm successor, offline until explicit activation.

The stopped parent and all prior outputs are immutable. Only previously
unstarted news C/B and up to 13 new status observations can be dispatched.
"""
import datetime as dt,json,sys
from decimal import Decimal,InvalidOperation
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-p1-cpi-recovery-v1'))
sys.path.insert(0,str(ROOT/'forecast-p1-budget-successor-v1'))
import recovery_ledger as old,p1_retry as retry,p1_budget as p,reconstruct,history
from ledger import canonical,digest,valid_hash
PARENT=reconstruct.PARENT
PARENT_SHA=reconstruct.PARENT_SHA
RECON=ROOT/'forecast-cpi-p1-no-news-reconstruction-20261029-v1.json'
RECON_SHA='b64e514a36017bb7b97b2b4349973b05fb947961c7b0f9d344f61d49b6b3784f'
class Error(ValueError):pass

def config():
 c=old.config();c.update(run_id='faithful-cpi-p1-38-successor-20261029-01',prior_micro=2069419,prior_generations=315,prior_counts=244,max_sources=13,source_cap_micro=1950000)
 return c

def inspect_parent():
 old.inspect_parent();h=history.History(PARENT,PARENT_SHA)
 if h.run!=(1,2069419,315,244,2) or h.extra_used!=0:raise Error('unexpected stopped predecessor usage or 429 retry carry')
 if any(':news:' in ident for ident in h.by_logical):raise Error('news already started; not this successor')
 if set(h.by_logical)!={f'{kind}:p1:case-02:no_news:b:{i:02d}' for i in range(1,9) for kind in ('count','generation')}:raise Error('unexpected model identities')
 if p.read(RECON,RECON_SHA)!=canonical(reconstruct.bundle()):raise Error('reconstructed no-news changed')
 return {'parent_db_sha256':PARENT_SHA,'prior_exposure_micro':2069419,'prior_generations':315,'prior_counts':244,'prior_sources':25,'prior_p1_429_extra':0,'reconstructed_no_news_sha256':RECON_SHA}

class Base(old.RecoveryBase):
 @staticmethod
 def _validate_contract(c):
  if c!=config():raise Error('successor accounting config differs')
 def _admit(self,logical,kind):
  prefix='count:' if kind=='count' else 'generation:'
  import re
  if not re.fullmatch(prefix+r'p1:case-02:news:(?:b|c):(?:0[1-9]|1[0-9]|2[0-3])',logical):raise Error('only unstarted news C/B permitted')

class Stage:
 def __init__(self,base,model_guard,source_guard,operations):
  if not isinstance(base,Base) or not callable(model_guard) or not callable(source_guard) or not isinstance(operations,list) or [x.get('ticket',{}).get('id') for x in operations]!=[f'p1-cpi-status-{i:02d}' for i in range(6,19)]:raise Error('invalid stage or status scope')
  self.base=base;self.guard=model_guard;self.source_guard=source_guard;self.ops=operations
 def summary(self):
  s=self.base.summary();s['source_attempts']+=25;s['previous_source_attempts']=25;return s
 def stop(self,reason):self.base.stop(reason)
 def _model_guard(self):
  if self.guard() is not True:raise Error('model guard failed')
 def count_attempt(self,*a):self._model_guard();return self.base.count_attempt(*a)
 def generate_attempt(self,*a):self._model_guard();return self.base.generate_attempt(*a)
 def status_source(self,ident,transport,verify_ticket):
  if self.source_guard() is not True or not callable(verify_ticket):raise Error('source guard failed')
  selected=[x for x in self.ops if x.get('ticket',{}).get('id')==ident]
  if len(selected)!=1:raise Error('status ID not authorized')
  op=selected[0];ticket=op['ticket'];raw=canonical(op['payload'])
  if op.get('kind')!='status_refresh' or op['payload']!={'api':'kalshi','path':'/markets','body':{},'query':{'tickers':'KXCPI-26OCT-T0.2'}} or ticket.get('request_sha256')!=digest(raw) or ticket.get('max_micro')!=150000 or (ticket.get('provider'),ticket.get('endpoint'),ticket.get('category'),ticket.get('settlement'))!=('orthogonal','/v1/run','market','orthogonal_price_cents') or not valid_hash(ticket.get('evidence_sha256')) or dt.datetime.now(dt.timezone.utc)>=dt.datetime.fromisoformat(ticket['expires_utc'].replace('Z','+00:00')) or verify_ticket(ticket,raw) is not True:raise Error('status ticket invalid')
  answer=self.base._execute(ident,'source','orthogonal','/v1/run',raw,150000,ticket['evidence_sha256'],transport,quote_metadata=canonical(ticket))
  try:
   x=json.loads(answer);price=Decimal(str(x['priceCents']))*10000;charged=Decimal(str(x['billing']['chargedPriceCents']))*10000
   if not price.is_finite() or not charged.is_finite() or price<0 or charged<0 or price!=price.to_integral_value() or charged!=charged.to_integral_value():raise ValueError('invalid price')
  except (ValueError,KeyError,TypeError,InvalidOperation):self.base._stop(ident,'source billing invalid; reserve retained');raise Error('source billing invalid') from None
  self.base._settle(ident,int(charged))
  if x.get('success') is not True or price!=charged:self.base.stop('source envelope or billing mismatch');raise Error('source response mismatch')
  return answer
 def receipt(self,ident):return self.base.receipt(ident)
