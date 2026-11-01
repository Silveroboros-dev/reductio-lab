"""Admit Serper News from an attributed dashboard observation, not /v1/details.

Offline functions only; the caller injects a single-run ledger and transport.
No checksum can establish who observed the UI, account binding, billing policy,
or a provider-enforced maximum. These must be independently reviewed before
live dispatch. Never treat this module as a stand-alone authorization.
"""
from __future__ import annotations
import copy
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Callable

_ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(_ROOT/'source-adapter'))
import serper

URL='https://www.orthogonal.com/dashboard/discover/serper/91fb13eb-b5bd-4602-849f-a87d7df01e75'
PRICE_MICRO=2_000
RISK_RESERVE_MICRO=250_000
FRESH_SECONDS=900

class AdmissionError(ValueError): pass
class EvidenceError(RuntimeError): pass

def _parse(raw):
    if not isinstance(raw,bytes) or len(raw)>200_000: raise AdmissionError('bounded observation bytes required')
    try: value=json.loads(raw,object_pairs_hook=serper._pairs)
    except (ValueError,UnicodeDecodeError,TypeError) as exc: raise AdmissionError('invalid observation') from exc
    if not isinstance(value,dict): raise AdmissionError('observation must be an object')
    return value

def bind_quote(request: bytes, observation: bytes, *, expected_sha256: str,
               verify_provenance: Callable, now: dt.datetime | None = None) -> dict:
    """Pin an observed dashboard price to an exact source request.

    expected_sha256 must come from a separately frozen contract. The supplied
    verifier owns independent provenance/account checks and is not itself proof.
    """
    if not isinstance(expected_sha256,str) or len(expected_sha256)!=64 or any(c not in '0123456789abcdef' for c in expected_sha256):
        raise AdmissionError('frozen observation hash required')
    if not isinstance(observation,bytes) or hashlib.sha256(observation).hexdigest()!=expected_sha256:
        raise AdmissionError('observation digest mismatch')
    if not callable(verify_provenance) or verify_provenance(observation) is not True:
        raise AdmissionError('dashboard provenance and account must be verified')
    view=_parse(observation)
    required={'observation','observed_at_utc','url','provider','api','path','method',
              'reported_rate','scope','additional_fields_observed','credential_identity','limits','transport'}
    if set(view)!=required: raise AdmissionError('exact UI observation schema required')
    if view['url']!=URL or (view['provider'],view['api'],view['path'],view['method'])!=('orthogonal','serper','/news','POST'):
        raise AdmissionError('dashboard endpoint identity mismatch')
    if view['reported_rate']!='$0.002 per call' or view['scope']!='first page; one non-paginated query with q and num':
        raise AdmissionError('fixed first-page USD price must be observed')
    fields=view['additional_fields_observed']
    if not isinstance(fields,list) or 'q required string' not in fields or 'num number default 10 max 100' not in fields:
        raise AdmissionError('required parameter evidence missing')
    if not isinstance(view['observation'],str) or not view['observation'].startswith('Direct visible inspection of authenticated Orthogonal dashboard'):
        raise AdmissionError('must be an attributed UI observation')
    if view['credential_identity']!='Keychain configured credential suffix matches default dashboard key, checked in memory without displaying credential':
        raise AdmissionError('account binding absent')
    seen=serper._utc(view['observed_at_utc'])
    if now is None: now=dt.datetime.now(dt.timezone.utc)
    if not isinstance(now,dt.datetime) or now.tzinfo is None: raise AdmissionError('aware observation time required')
    now=now.astimezone(dt.timezone.utc)
    if seen>now or (now-seen).total_seconds()>FRESH_SECONDS: raise AdmissionError('UI observation stale or future')
    obj=serper._decode(request)
    if not isinstance(obj,dict) or set(obj)!={'api','path','body','query'} or obj.get('api')!='serper' or obj.get('path')!='/news' or obj.get('query')!={}: raise AdmissionError('wrong request envelope')
    body=obj.get('body')
    if not isinstance(body,dict) or set(body)!={'q','num'} or serper.build_request(body.get('q'),body.get('num'))!=request:
        raise AdmissionError('first-page bounded canonical request required')
    return {'provider':'orthogonal','endpoint':'/v1/run','request_sha256':serper.sha(request),
            'max_micro':RISK_RESERVE_MICRO,'evidence_sha256':expected_sha256,
            'expires_utc':(seen+dt.timedelta(seconds=FRESH_SECONDS)).isoformat().replace('+00:00','Z')}

def _request_id(value):
    candidates=[]
    if value.get('requestId') is not None: candidates.append(value['requestId'])
    billing=value.get('billing')
    if billing is not None:
        if not isinstance(billing,dict): raise EvidenceError('invalid billing object')
        if billing.get('requestId') is not None: candidates.append(billing['requestId'])
    if not candidates or any(not isinstance(x,str) or not 1<=len(x)<=256 for x in candidates) or len(set(candidates))!=1:
        raise EvidenceError('missing or inconsistent request id')
    return candidates[0]

def execute(ledger, op_id, request, observation, *, expected_sha256, verify_provenance, transport, now=None):
    """Call only the injected ledger; preserve exact response and effect truth."""
    if not callable(transport) or any(not callable(getattr(ledger,m,None)) for m in ('source','receipt','stop')):
        raise AdmissionError('ledger and one-shot transport required')
    quote=bind_quote(request,observation,expected_sha256=expected_sha256,verify_provenance=verify_provenance,now=now)
    raw=ledger.source(op_id,'orthogonal','/v1/run',request,quote,transport)
    try:
        result=serper._decode(raw)
        if not isinstance(result,dict) or result.get('success') is not True or not isinstance(result.get('data'),dict):
            raise EvidenceError('invalid source wrapper')
        rid=_request_id(result)
        receipt=ledger.receipt(op_id)
        if (not isinstance(receipt,dict) or receipt.get('state')!='succeeded' or receipt.get('http_status')!=200
            or receipt.get('kind')!='source' or receipt.get('provider')!='orthogonal' or receipt.get('endpoint')!='/v1/run'
            or receipt.get('request')!=request or receipt.get('request_hash')!=serper.sha(request)
            or receipt.get('response')!=raw or receipt.get('response_hash')!=serper.sha(raw)
            or type(receipt.get('actual_micro')) is not int or not 0<=receipt['actual_micro']<=quote['max_micro']
            or receipt.get('quote_micro')!=quote['max_micro'] or receipt.get('quote_evidence_sha')!=quote['evidence_sha256']):
            raise EvidenceError('source receipt mismatch')
        serper._utc(receipt.get('completed_at_utc'))
        # Advertised first-page charge and local cost-risk reserve are distinct.
        # A lower actual charge may reflect a credit; an unexpectedly HIGHER
        # charge is preserved as succeeded/actual, then stops the run.
        if receipt['actual_micro'] > PRICE_MICRO:
            raise EvidenceError('actual charge exceeded displayed first-page price')
        # Return only diagnostic metadata, not content; caller can read the raw
        # ledger receipt and build verbatim, separately scoped evidence.
        return {'request_id':rid,'request_sha256':serper.sha(request),'response_sha256':serper.sha(raw),
                'captured_at_utc':receipt['completed_at_utc'],'price_micro_usd':receipt['actual_micro'],
                'advertised_price_micro_usd':PRICE_MICRO,'risk_reserve_micro_usd':quote['max_micro'],
                'quote_evidence_sha256':quote['evidence_sha256'],
                'quote_evidence_kind':'attributed_dashboard_observation'}
    except Exception as exc:
        ledger.stop('invalid source wrapper or receipt')
        raise EvidenceError('effect completed but evidence admission failed; run stopped') from exc
