"""Offline Serper News adapter, with injected ledger/transport. No network client.

A digest is an integrity binding, not proof of origin, price unit, or billing.
Before live use a governed external capture must bind /v1/details to actual
provider bytes and the account, then be reviewed against the current API terms.
"""
from __future__ import annotations
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

API='serper'
PATH='/news'
PROVIDER='orthogonal'
RUN_ENDPOINT='/v1/run'
DETAILS_ENDPOINT='/v1/details'
MAX_PRICE_MICRO=250_000
MAX_DETAILS_AGE_SECONDS=900
MAX_RESPONSE_BYTES=2_097_152

class AdmissionError(ValueError): pass
class EvidenceError(RuntimeError): pass

def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')

def sha(data): return hashlib.sha256(data).hexdigest()

def _pairs(pairs):
    result={}
    for k,v in pairs:
        if k in result: raise AdmissionError('duplicate JSON key')
        result[k]=v
    return result

def _decode(raw):
    if not isinstance(raw,bytes) or len(raw)>MAX_RESPONSE_BYTES: raise AdmissionError('invalid or oversized raw bytes')
    try:
        return json.loads(raw, parse_float=Decimal, parse_constant=lambda _: (_ for _ in ()).throw(AdmissionError('invalid number')), object_pairs_hook=_pairs)
    except (UnicodeDecodeError,json.JSONDecodeError) as e: raise AdmissionError('invalid JSON') from e

def _utc(value):
    if not isinstance(value,str): raise AdmissionError('UTC timestamp required')
    try: parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as e: raise AdmissionError('invalid timestamp') from e
    if parsed.tzinfo is None: raise AdmissionError('timezone required')
    return parsed.astimezone(dt.timezone.utc)

def details_request(): return canonical({'api':API,'path':PATH})

def build_request(query, num=3):
    """Only a bounded, non-paginated Serper News query is supported."""
    if not isinstance(query,str) or not query.strip() or len(query)>500 or any(ord(c)<32 for c in query):
        raise AdmissionError('query must contain 1..500 printable characters')
    if type(num) is not int or not 1<=num<=3: raise AdmissionError('num must be 1..3')
    request=canonical({'api':API,'path':PATH,'body':{'q':query,'num':num},'query':{}})
    if len(request)>8192: raise AdmissionError('request exceeds limit')
    return request

def _price_micro(endpoint):
    dynamic=endpoint.get('hasDynamicPricing')
    if dynamic is not None and type(dynamic) is not bool: raise AdmissionError('invalid dynamic flag')
    if dynamic is True: raise AdmissionError('dynamic pricing rejected')
    if endpoint.get('priceCurrency', 'USD') != 'USD': raise AdmissionError('unexpected price currency')
    if endpoint.get('currency', 'USD') != 'USD': raise AdmissionError('unexpected currency')
    for field in ('pricingUnit','priceUnit','unit'):
        if field in endpoint and endpoint[field] not in ('request','call','per_request','per_call','USD/request'):
            raise AdmissionError('unsupported pricing unit')
    value=endpoint.get('price')
    if isinstance(value,str):
        if not re.fullmatch(r'\$\d+(?:\.\d{1,6})?',value): raise AdmissionError('price not a fixed dollar-per-call quote')
        value=value[1:]
    elif isinstance(value,(int,Decimal)) and not isinstance(value,bool):
        if dynamic is not False: raise AdmissionError('numeric price must explicitly be fixed')
    else: raise AdmissionError('invalid fixed price')
    try: micro=Decimal(str(value))*1_000_000
    except InvalidOperation as e: raise AdmissionError('invalid price') from e
    if not micro.is_finite() or micro != micro.to_integral_value() or not 0 < micro <= MAX_PRICE_MICRO:
        raise AdmissionError('price outside exact whole-request budget')
    return int(micro)

def bind_quote(request, capture, *, now=None):
    """Bind a supplied direct /v1/details capture to one exact request.

    Capture schema: provider, endpoint, request, response, response_sha256,
    http_status, started_at_utc, completed_at_utc. This checks structural
    evidence; the caller is responsible for provenance of the capture itself.
    """
    if not isinstance(request,bytes): raise AdmissionError('request bytes required')
    expected={'provider','endpoint','request','response','response_sha256','http_status','started_at_utc','completed_at_utc'}
    if not isinstance(capture,dict) or set(capture)!=expected: raise AdmissionError('exact metadata capture required')
    if capture['provider']!=PROVIDER or capture['endpoint']!=DETAILS_ENDPOINT or capture['request']!=details_request() or capture['http_status']!=200:
        raise AdmissionError('metadata request identity/status mismatch')
    raw=capture['response']
    if not isinstance(raw,bytes) or sha(raw)!=capture['response_sha256']: raise AdmissionError('metadata response digest mismatch')
    started, completed = _utc(capture['started_at_utc']), _utc(capture['completed_at_utc'])
    current=now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(current,dt.datetime) or current.tzinfo is None: raise AdmissionError('aware current time required')
    current=current.astimezone(dt.timezone.utc)
    if started>completed or completed>current or (current-completed).total_seconds()>MAX_DETAILS_AGE_SECONDS:
        raise AdmissionError('metadata capture stale or inconsistent')
    value=_decode(raw)
    if not isinstance(value,dict) or value.get('success') is not True: raise AdmissionError('metadata not successful')
    api, endpoint=value.get('api'),value.get('endpoint')
    if not isinstance(api,dict) or api.get('slug')!=API or not isinstance(endpoint,dict): raise AdmissionError('metadata provider mismatch')
    if endpoint.get('path')!=PATH or endpoint.get('method')!='POST' or endpoint.get('isPayable') is not True:
        raise AdmissionError('metadata endpoint identity mismatch')
    if 'endpoints' in value and (not isinstance(value['endpoints'],list) or endpoint not in value['endpoints']):
        raise AdmissionError('metadata endpoint listing mismatch')
    max_micro=_price_micro(endpoint)
    # Restrict quote to a request generated by this adapter, with no unchecked extra fields.
    obj=_decode(request)
    if not isinstance(obj,dict) or set(obj)!={'api','path','body','query'} or obj['api']!=API or obj['path']!=PATH or obj['query']!={}:
        raise AdmissionError('wrong execution envelope')
    b=obj['body']
    if not isinstance(b,dict) or set(b)!={'q','num'} or build_request(b['q'],b['num'])!=request:
        raise AdmissionError('noncanonical or unsupported provider body')
    expiry=completed+dt.timedelta(seconds=MAX_DETAILS_AGE_SECONDS)
    return {'provider':PROVIDER,'endpoint':RUN_ENDPOINT,'request_sha256':sha(request),
            'max_micro':max_micro,'evidence_sha256':sha(raw),
            'expires_utc':expiry.isoformat().replace('+00:00','Z')}

def execute(ledger, op_id, request, capture, transport, *, now=None):
    """Run one source op through the injected ledger; transport must be one-shot.

    Response bytes live in the ledger. The returned projections are candidates,
    not review decisions or proof of source timestamp/semantic correctness.
    """
    if not callable(transport) or not callable(getattr(ledger,'source',None)) or not callable(getattr(ledger,'receipt',None)) or not callable(getattr(ledger,'stop',None)):
        raise AdmissionError('injected ledger and transport required')
    quote=bind_quote(request,capture,now=now)
    raw=ledger.source(op_id,PROVIDER,RUN_ENDPOINT,request,quote,transport)
    try:
        receipt=ledger.receipt(op_id)
        data=_decode(raw)
        if not isinstance(data,dict) or data.get('success') is not True or 'data' not in data:
            raise EvidenceError('invalid provider wrapper')
        request_id=data.get('requestId')
        if not isinstance(request_id,str) or not 1<=len(request_id)<=256:
            raise EvidenceError('missing provider request ID')
        if (not isinstance(receipt,dict) or receipt.get('state')!='succeeded' or receipt.get('http_status')!=200
            or receipt.get('kind')!='source' or receipt.get('provider')!=PROVIDER or receipt.get('endpoint')!=RUN_ENDPOINT
            or receipt.get('response')!=raw or receipt.get('request')!=request
            or receipt.get('response_hash')!=sha(raw) or receipt.get('request_hash')!=sha(request)
            or type(receipt.get('actual_micro')) is not int or not 0<=receipt['actual_micro']<=quote['max_micro']
            or receipt.get('quote_micro')!=quote['max_micro'] or receipt.get('quote_evidence_sha')!=quote['evidence_sha256']):
            raise EvidenceError('ledger receipt does not bind source capture')
        captured_at=receipt.get('completed_at_utc')
        _utc(captured_at)
        return {'provider':PROVIDER,'api':API,'endpoint':PATH,'run_endpoint':RUN_ENDPOINT,
                'request_id':request_id,'request_sha256':sha(request),'response_sha256':sha(raw),
                'captured_at_utc':captured_at,'price_micro_usd':receipt['actual_micro'],
                'quote_micro_usd':quote['max_micro'],'quote_evidence_sha256':quote['evidence_sha256'],
                'data':json.loads(raw,object_pairs_hook=_pairs,parse_constant=lambda _: (_ for _ in ()).throw(AdmissionError('invalid number')))['data']}
    except Exception as exc:
        # Actual effect remains succeeded/accounted; failed semantic capture must
        # block further live dispatch, not be reclassified as no effect.
        ledger.stop('invalid Serper response/capture')
        raise EvidenceError('source effect recorded but evidence admission failed; stop the run') from exc
