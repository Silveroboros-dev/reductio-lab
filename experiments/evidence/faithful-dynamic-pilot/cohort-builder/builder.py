"""Create-only successor binding settled paid captures to eight approved cases.

Offline only. The injected ledger must be the same ledger that recorded the
source operations; no service, credential, reviewer, or live effect is created.
An admissible cohort is not evidence of its semantic correctness or novelty.
"""
from __future__ import annotations
import copy
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
PREDECESSOR_SHA='7219ea98341b5dcaa025653cfcc70e68edc593ca8cde5fa2170cdc1f598dd8cd'
UI_QUOTE_SHA='b77cd7bd9f5264879dc3b4b7db3cd73f1d2a836995258c4a206a91671e0e8ac9'

class AdmissionError(ValueError): pass

def digest(b): return hashlib.sha256(b).hexdigest()
def encode(v): return (json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def canonical(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()

def pairs(items):
    d={}
    for k,v in items:
        if k in d: raise AdmissionError('duplicate JSON key')
        d[k]=v
    return d

def decode(raw):
    try: return json.loads(raw,parse_float=Decimal,object_pairs_hook=pairs)
    except (ValueError,TypeError,UnicodeDecodeError) as exc: raise AdmissionError('invalid JSON') from exc

def timestamp(value):
    try: out=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    except (AttributeError,TypeError,ValueError) as exc: raise AdmissionError('invalid timestamp') from exc
    if out.tzinfo is None: raise AdmissionError('timezone required')
    return out.astimezone(dt.timezone.utc)

def read_bound(root,rel,expected):
    if not isinstance(rel,str) or not rel or not isinstance(expected,str): raise AdmissionError('missing path or hash')
    p=root/rel
    if not p.resolve().is_relative_to(root) or p.absolute()!=p.resolve() or not p.is_file(): raise AdmissionError('unsafe or missing attachment')
    raw=p.read_bytes()
    if digest(raw)!=expected: raise AdmissionError('attachment hash mismatch')
    return raw

def put(root,rel,raw):
    p=root/rel; p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    with p.open('xb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    fd=os.open(p.parent,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)
    return {'path':rel,'sha256':digest(raw)}

def request_for(body):
    if not isinstance(body,dict) or set(body)!={'q','num'} or not isinstance(body['q'],str) or not body['q'].strip() or len(body['q'])>500 or type(body['num']) is not int or body['num']!=3:
        raise AdmissionError('invalid predeclared query')
    return canonical({'api':'serper','path':'/news','body':body,'query':{}})

def extract_news(raw):
    data=decode(raw)
    if not isinstance(data,dict) or data.get('success') is not True or not isinstance(data.get('data'),dict): raise AdmissionError('invalid source envelope')
    top=data.get('requestId'); billing=data.get('billing')
    nested=billing.get('requestId') if isinstance(billing,dict) else None
    if top is not None and nested is not None and top!=nested: raise AdmissionError('provider request IDs disagree')
    rid=top or nested
    if not isinstance(rid,str) or not rid.strip(): raise AdmissionError('provider request ID absent')
    items=data['data'].get('news')
    if not isinstance(items,list) or len(items)>3: raise AdmissionError('news array missing or outside bound')
    evidence=[]
    for i,item in enumerate(items):
        if not isinstance(item,dict): raise AdmissionError('news entry must be object')
        for field in ('title','link','source','date','snippet'):
            value=item.get(field)
            if value is None or value=='': continue
            if not isinstance(value,str): raise AdmissionError('news field must be text')
            evidence.append((f'news:{i}:{field}',value))
    return data,rid,evidence

def validate_receipt(ledger,op_id,expected_request,quote_bytes,query_fixed_at,verify_quote):
    try: r=ledger.receipt(op_id)
    except (KeyError,AttributeError) as exc: raise AdmissionError('settled effect missing') from exc
    if not isinstance(r,dict) or r.get('id')!=op_id or r.get('kind')!='source' or r.get('provider')!='orthogonal' or r.get('endpoint')!='/v1/run' or r.get('state')!='succeeded' or r.get('http_status')!=200:
        raise AdmissionError('source receipt state or identity invalid')
    raw=r.get('response'); request=r.get('request')
    if not isinstance(raw,bytes) or not isinstance(request,bytes) or request!=expected_request or digest(request)!=r.get('request_hash') or digest(raw)!=r.get('response_hash'):
        raise AdmissionError('source request or response binding differs')
    if r.get('quote_evidence_sha')!=digest(quote_bytes) or digest(quote_bytes)!=UI_QUOTE_SHA:
        raise AdmissionError('UI price evidence does not bind receipt')
    quote=decode(r.get('quote_metadata'))
    if (not isinstance(quote,dict) or set(quote)!={'provider','endpoint','request_sha256','max_micro','evidence_sha256','expires_utc'} or
        quote['provider']!='orthogonal' or quote['endpoint']!='/v1/run' or quote['request_sha256']!=digest(request) or
        quote['evidence_sha256']!=UI_QUOTE_SHA or quote['max_micro']!=250000 or r.get('quote_micro')!=250000):
        raise AdmissionError('quote identity or price mismatch')
    start,end=timestamp(r.get('started_at_utc')),timestamp(r.get('completed_at_utc'))
    if end<start or start<timestamp(query_fixed_at) or start>=timestamp(quote['expires_utc']): raise AdmissionError('capture timestamp outside bound quote')
    if not callable(verify_quote) or verify_quote(quote_bytes,copy.deepcopy(quote),copy.deepcopy(r)) is not True:
        raise AdmissionError('independent price provenance not verified')
    response,rid,leaves=extract_news(raw)
    try:
        cents=Decimal(str(response['priceCents']))
        micro=cents*10000
        if not micro.is_finite() or micro<0 or micro!=micro.to_integral_value() or int(micro)!=r.get('actual_micro') or int(micro)>2000:
            raise ValueError('price mismatch')
    except (KeyError,InvalidOperation,ValueError,TypeError) as exc: raise AdmissionError('actual source charge missing or inconsistent') from exc
    return r,rid,leaves

def build(predecessor_root, output_root, ledger, quote_evidence, verify_quote, verify_human, verify_capture):
    """Build successor after all 8 captures; invoke independent preflight before success.

    `verify_quote`, `verify_human`, `verify_capture` are mandatory external
    verification functions. A callback that merely returns True is not evidence.
    """
    pred=Path(predecessor_root).resolve(); out=Path(output_root).absolute()
    if out.exists() or out.is_symlink(): raise AdmissionError('successor path already exists')
    if not pred.is_dir() or not callable(verify_human) or not callable(verify_capture): raise AdmissionError('independent verifiers required')
    manifest_raw=(pred/'manifest.json').read_bytes()
    if digest(manifest_raw)!=PREDECESSOR_SHA: raise AdmissionError('predecessor manifest drift')
    manifest=decode(manifest_raw)
    if manifest.get('schema')!='faithful-dynamic-draft-manifest-v1' or manifest.get('runnable') is not False or len(manifest.get('cases',[]))!=8:
        raise AdmissionError('expected eight-case draft predecessor')
    quote_bytes=Path(quote_evidence).read_bytes()
    if digest(quote_bytes)!=UI_QUOTE_SHA: raise AdmissionError('UI observation bytes changed')
    rows=manifest['cases']; unique_ids={r['case_id'] for r in rows}; groups={r['event_group_id'] for r in rows}
    if len(unique_ids)!=8 or len(groups)!=8 or [r['split'] for r in rows].count('dev')!=2 or [r['split'] for r in rows].count('test')!=6: raise AdmissionError('cohort identity or split invalid')
    if ledger.summary().get('stopped'): raise AdmissionError('ledger stopped')
    prepared=[]
    for row in rows:
        case_raw=read_bound(pred,row['input_path'],row['input_sha256']); case=decode(case_raw)
        if case['task']['case_id']!=row['case_id'] or len(case['task']['actions'])!=1 or case['task']['actions'][0]['id']!='manual-rules': raise AdmissionError('draft case or action changed')
        draft=case['draft_paid_source']
        if draft.get('quote_status')!='not obtained' or draft.get('response_status')!='not captured' or draft.get('response') is not None or draft.get('quoted_cost_micro_usd') is not None: raise AdmissionError('predecessor contains fabricated paid evidence')
        body=draft['request_body']; op_id='source:'+row['case_id']+':serper'
        receipt,rid,leaves=validate_receipt(ledger,op_id,request_for(body),quote_bytes,draft['query_fixed_at_utc'],verify_quote)
        # Existing attachments and human decision are all re-validated by bytes.
        for a in case['attachments']: read_bound(pred,a['path'],a['sha256'])
        read_bound(pred,row['human_attestation_path'],row['human_attestation_sha256'])
        prepared.append((row,case,receipt,rid,leaves))
    if len({x[2]['id'] for x in prepared})!=8 or len({x[3] for x in prepared})!=8: raise AdmissionError('source operation or provider request ID repeats')
    out.mkdir(mode=0o700,parents=False)
    put(out,'predecessor/manifest-v2.json',manifest_raw)
    qref=put(out,'source/ui-price-observation.json',quote_bytes)
    new_rows=[]
    for row,case,receipt,rid,leaves in prepared:
        # Preserve all predecessor-bound files once; names and bytes remain exact.
        for item in case['attachments']:
            dest=out/item['path']; raw=read_bound(pred,item['path'],item['sha256'])
            if dest.exists():
                if dest.read_bytes()!=raw: raise AdmissionError('conflicting shared attachment')
            else: put(out,item['path'],raw)
        human=read_bound(pred,row['human_attestation_path'],row['human_attestation_sha256'])
        if not (out/row['human_attestation_path']).exists(): put(out,row['human_attestation_path'],human)
        raw=receipt['response']; ref=put(out,f"source/{row['case_id']}-serper-response.json",raw)
        facts=[{'id':identity,'text':text,'source':'Serper News via Orthogonal; '+identity,
                'captured_at':receipt['completed_at_utc'],'content_sha256':ref['sha256'],'verbatim_parts':[text]}
               for identity,text in leaves]
        news={'id':'news','description':'Read Serper News results for query: '+case['draft_paid_source']['request_body']['q'],
              'capture_kind':'paid_api','quoted_cost_micro_usd':2000,
              'source_effect_id':receipt['id'],'captured_at':receipt['completed_at_utc']}
        case['task']['actions'].append(news)
        case['replay']['news']={'evidence':facts}
        case['attachments'].extend([ref,qref])
        case['paid_capture']={'source_effect_id':receipt['id'],'provider_request_id':rid,
                              'response_sha256':ref['sha256'],'actual_micro_usd':receipt['actual_micro'],
                              'quote_evidence_sha256':UI_QUOTE_SHA,'news_item_fields':len(facts)}
        # Keep historical draft for lineage; it is not projected to the model.
        case_ref=put(out,row['input_path'],encode(case))
        row=copy.deepcopy(row);row['input_sha256']=case_ref['sha256'];new_rows.append(row)
    result={'schema':'faithful-dynamic-pilot-manifest-v1','cases':new_rows,
            'predecessor_sha256':PREDECESSOR_SHA,'ui_quote_sha256':UI_QUOTE_SHA,
            'semantic_review':'not performed','external_seal':'not established',
            'limitations':['manual Kalshi origin user-relayed','Fed source conflict unresolved',
                           'one market per event','semantic novelty not established',
                           'callback truth and independence require external evidence']}
    put(out,'manifest.json',encode(result))
    import sys
    sys.path.insert(0,str(ROOT/'runner-ui'))
    import runner_ui
    try: runner_ui.preflight(result,out.resolve(),ledger,verify_human,verify_capture)
    except Exception as exc: raise AdmissionError('successor fails independent runner preflight; preserve output for diagnosis') from exc
    return result
