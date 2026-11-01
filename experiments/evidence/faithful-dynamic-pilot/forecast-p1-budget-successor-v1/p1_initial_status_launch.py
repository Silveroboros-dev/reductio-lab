"""One initial CPI status observation after BEA source capture; no model."""
import json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'forecast-p1-budget-successor-v1'))
import p1_retry as r
import p1_budget as p
import retry_accounting_launch as a
import p1_source_launch as s
PACKET=ROOT/'forecast-cpi-p1-status-challenge-packet-v1.json'
RECEIPT=ROOT/'forecast-cpi-p1-status-challenge-receipt-v1.json'
OUTPUT=ROOT/'forecast-cpi-p1-initial-status-results-20261029-01'
EVENT_SUMMARY=ROOT/'forecast-cpi-p1-event-results-20261029-01/summary.json'
EVENT_RAW=ROOT/'forecast-cpi-p1-event-results-20261029-01/event.raw.json'
EVENT_DB=a.LEDGER/'ledger.sqlite3'
EVENT_SUMMARY_SHA='c2c82782be0a312fa5d5a6ec169ff1064668f56fc1075998d95ac4ea480581e5'
EVENT_RAW_SHA='f3cd83fafc54825f6310d29b34bfd7d830a8c914365d55d6c1b30037e59919d2'
EVENT_DB_SHA='cbea8ec4f2550d949edeaa0438e1d1601fd17e5e6ccc9950d4754905e024df3d'
FILES=('forecast-p1-budget-successor-v1/p1_initial_status_launch.py',*s.FILES)

def verify():
 c,cr,_,_=s.verify(s.SOURCE_SHA);er=p.read(EVENT_SUMMARY,EVENT_SUMMARY_SHA);p.read(EVENT_RAW,EVENT_RAW_SHA);p.read(EVENT_DB,EVENT_DB_SHA);event=json.loads(er)
 if event.get('contract_sha256')!=s.SOURCE_SHA or event.get('status')!='captured_not_yet_eligible' or event.get('receipt',{}).get('response_hash')!=EVENT_RAW_SHA or event.get('ledger',{}).get('source_attempts')!=20:raise p.Error('event lineage mismatch')
 pr,rr=map(p.read,(PACKET,RECEIPT));w,receipt=map(json.loads,(pr,rr));d=w.get('internal_digest')
 if w.get('schema_version')!='eval_contract_challenge_packet_v1' or w.get('overall_state')!='ready' or w.get('witness',{}).get('identity')!='cpi_p1_initial_status_witness' or w.get('witness',{}).get('mode')!='read_only_offline' or w.get('challenged_contract',{}).get('raw_sha256')!=s.SOURCE_SHA or d!=p.digest(p.canonical({k:v for k,v in w.items() if k!='internal_digest'})) or receipt.get('packet_raw_sha256')!=p.digest(pr) or receipt.get('packet_byte_count')!=len(pr) or receipt.get('packet_internal_digest')!=d or receipt.get('state')!='ready':raise p.Error('independent status review mismatch')
 context=w.get('context_binding',{});observed=context.get('code_bindings_at_inspection',{})
 for name in FILES:
  raw=p.read(ROOT/name)
  if observed.get(name)!={'sha256':p.digest(raw),'size':len(raw)}:raise p.Error('code changed after status review')
 if context.get('event_summary_sha256')!=EVENT_SUMMARY_SHA or context.get('event_raw_sha256')!=EVENT_RAW_SHA or context.get('event_ledger_sha256')!=EVENT_DB_SHA or context.get('operation_id')!='p1-cpi-status-01':raise p.Error('status review lineage mismatch')
 return c,cr,pr,rr

def execute():
 """One source attempt, no source retry, no model, no automatic trade."""
 c,cr,pr,rr=verify()
 if Path.cwd().resolve()!=ROOT or OUTPUT.exists():raise p.Error('unsafe output')
 def account_ok(raw):
  try:return a.verify(s.ACCOUNT_SHA)[1]==raw
  except Exception:return False
 def source_ok(raw):
  try:return s.verify(s.SOURCE_SHA)[1]==raw
  except Exception:return False
 def ticket_ok(ticket,raw):return source_ok(cr) and any(x['ticket']==ticket and p.canonical(x['payload'])==raw for x in c['operations'])
 def historical_ok(ticket,raw,started):return ticket_ok(ticket,raw)
 account,stage=r.reopen_after_source(a.LEDGER,contract_path=a.CONTRACT,contract_sha=s.ACCOUNT_SHA,verify_challenge=account_ok,source_path=s.CONTRACT,source_sha=s.SOURCE_SHA,verify_source_challenge=source_ok,verify_historical_ticket=historical_ok,verify_ticket=ticket_ok)
 try:
  OUTPUT.mkdir(mode=0o700);s.put(OUTPUT/'started.json',p.canonical({'source_contract_sha256':s.SOURCE_SHA,'challenge_sha256':p.digest(pr),'challenge_receipt_sha256':p.digest(rr),'id':'p1-cpi-status-01'}))
  def token(provider):
   if provider!='orthogonal':raise p.Error('model denied')
   v=subprocess.run(['/usr/bin/security','find-generic-password','-s','com.maguire.orthogonal.live','-a','maguire','-w'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False,timeout=15)
   if v.returncode or not v.stdout.strip():raise p.Error('credential unavailable')
   return v.stdout.strip().decode('ascii')
  sys.path.insert(0,str(ROOT/'transport'));from oneshot import OneShotTransport
  op=c['operations'][1];raw=stage.source(op['ticket']['id'],'orthogonal','/v1/run',p.canonical(op['payload']),op['ticket'],OneShotTransport('source-only-123',token));rec=stage.receipt(op['ticket']['id']);s.put(OUTPUT/'status.raw.json',raw)
  if rec['actual_micro']!=0:stage.stop('status billed above UI Free');raise p.Error('status price above observed UI')
  result={'schema':'cpi-p1-initial-status-capture-v1','status':'captured_not_yet_eligible','source_contract_sha256':s.SOURCE_SHA,'source_id':op['ticket']['id'],'receipt':{k:rec[k] for k in ('id','http_status','request_hash','response_hash','actual_micro','started_at_utc','completed_at_utc')},'ledger':account.summary(),'qualification':'Orthogonal provider observation; upstream cache/age not established. Inspect exact market, status and rules; no model was called.'}
  s.put(OUTPUT/'summary.json',p.canonical(result));return result
 except BaseException:
  if not account.base.summary()['stopped']:account.base.stop('P1 initial status capture failed; no retry')
  raise
 finally:account.close()
