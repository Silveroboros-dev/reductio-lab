import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

root = Path(__file__).resolve().parent
body = b'{"q":"Federal Reserve interest rate decision","num":3}'
url = 'https://x402.orthogonal.com/serper/news'
headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
request_manifest = {'method':'POST', 'url':url, 'headers':headers, 'body_utf8':body.decode(),
 'max_attempts':1, 'timeout_seconds':20, 'credential_mode':'none', 'payment_header':'none',
 'retry_policy':'never', 'scope':'price discovery on x402 only; no paid retry',
 'provider_contract':'https://docs.orthogonal.com/payments'}
manifest_bytes = json.dumps(request_manifest, sort_keys=True, separators=(',',':')).encode()

def exclusive(path, data):
 with open(path,'xb') as f:
  f.write(data); f.flush(); os.fsync(f.fileno())

def event(item):
 with open(root/'events.jsonl','ab') as f:
  f.write(json.dumps(item, sort_keys=True, separators=(',',':')).encode()+b'\n'); f.flush(); os.fsync(f.fileno())

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()

exclusive(root/'request.json',manifest_bytes)
digest=hashlib.sha256(manifest_bytes).hexdigest()
event({'state':'prepared','time':now(),'request_sha256':digest})
event({'state':'started','time':now(),'request_sha256':digest})
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self, req, fp, code, msg, hdrs, newurl): return None
opener=urllib.request.build_opener(NoRedirect())
req=urllib.request.Request(url, data=body, method='POST', headers=headers)
try:
 try:
  response=opener.open(req,timeout=20)
 except urllib.error.HTTPError as e:
  response=e
 raw=response.read(1048577)
 if len(raw)>1048576: raise RuntimeError('response_too_large')
 status=response.status
 offers={k.lower():v for k,v in response.headers.items() if k.lower() in {'payment-required','x-payment-required','content-type'}}
 exclusive(root/'response.bin',raw)
 exclusive(root/'response-headers.json',json.dumps(offers, sort_keys=True, separators=(',',':')).encode())
 sha=hashlib.sha256(raw).hexdigest()
 event({'state':'succeeded','time':now(),'http_status':status,'request_sha256':digest,'raw_response_sha256':sha,'header_sha256':hashlib.sha256((root/'response-headers.json').read_bytes()).hexdigest()})
 report={'http_status':status,'raw_response_sha256':sha,'header_names':list(offers),'body_length':len(raw),'request_sha256':digest}
 for key in ['payment-required','x-payment-required']:
  if key in offers:
   try:
    decoded=json.loads(base64.b64decode(offers[key]+'===', validate=False));
    report['payment_offer']={'x402Version':decoded.get('x402Version'),'accepts':[{'scheme':a.get('scheme'),'network':a.get('network'),'amount':a.get('amount'),'maxAmountRequired':a.get('maxAmountRequired'),'asset':a.get('asset')} for a in decoded.get('accepts',[])]}
   except Exception as e: report['decode_error']=type(e).__name__
 print(json.dumps(report))
except Exception as e:
 event({'state':'uncertain','time':now(),'error_type':type(e).__name__,'request_sha256':digest,'retry_forbidden':True})
 print(json.dumps({'state':'uncertain','error_type':type(e).__name__,'retry_forbidden':True,'request_sha256':digest}))
