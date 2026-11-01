"""Eight-case source-capture executor. Importing this file never performs I/O.

Not an authorization mechanism. A frozen contract, separately written challenge
and receipt, runtime/provenance review, and a user-authorized effect are needed.
Offline-fixture and live modes are explicitly distinct. There is no CLI dispatch.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
for _d in (ROOT/'budget-v2',ROOT/'transport',ROOT/'source-adapter',ROOT/'ui-quote-work'):
    sys.path.insert(0,str(_d))
import ui_quote
import serper
from ledger import Ledger, Stop
from oneshot import OneShotTransport

PRICE_SHA='b77cd7bd9f5264879dc3b4b7db3cd73f1d2a836995258c4a206a91671e0e8ac9'
DRAFT_SHA='66125dd9ce9d48e325e2d03f62f080928aa059645a10bdcbf9e5417bd2cac845'
REQUIRED_COMPONENTS=('ui-quote-work/source_capture.py','ui-quote-work/ui_quote.py',
    'budget-v2/ledger.py','transport/oneshot.py','source-adapter/serper.py',
    'dataset-draft-20261029/draft.json','ui-serper-price-20261029.json',
    'ui-quote-work/live_source_dispatch.py','live-ledger-contract-20261029.json',
    'live-pricing-evidence-20261029.json')
SCHEMA='faithful-source-capture-contract-v2'

class PreflightError(ValueError): pass

def sha(raw): return hashlib.sha256(raw).hexdigest()

def _read(p):
    p=Path(p)
    if p.is_symlink() or not p.is_file() or p.resolve()!=p.absolute():
        raise PreflightError('missing, relative or symlinked evidence path')
    return p.read_bytes()

def _json(raw):
    try:
        value=json.loads(raw,object_pairs_hook=serper._pairs)
    except (ValueError,TypeError,UnicodeDecodeError) as exc:
        raise PreflightError('malformed JSON') from exc
    if not isinstance(value,dict): raise PreflightError('JSON object required')
    return value

def _component_bytes(root, path):
    if not isinstance(path,str) or not path or Path(path).is_absolute():
        raise PreflightError('component path must be relative')
    p=(root/path)
    if not p.resolve().is_relative_to(root): raise PreflightError('component outside artifact root')
    return _read(p)

def _write_once(path, obj):
    raw=json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        n=0
        while n<len(raw):
            m=os.write(fd,raw[n:])
            if m<=0: raise OSError('short write')
            n+=m
        os.fsync(fd)
    finally: os.close(fd)
    fd=os.open(path.parent,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

def validate(contract_path, challenge_path, challenge_receipt_path, *, ledger, output_dir,
             verify_challenge, verify_ui, now=None):
    """Reject missing/changed bindings before credentials or provider effects.

    verify_challenge(packet_bytes, receipt_bytes, contract_bytes) and
    verify_ui(observation_bytes) are external trusted reviewers, not proofs.
    Passing callbacks that merely return True is NOT independent review.
    """
    if not callable(verify_challenge) or not callable(verify_ui):
        raise PreflightError('independent challenge and UI reviewers required')
    contract_raw=_read(contract_path); challenge_raw=_read(challenge_path); receipt_raw=_read(challenge_receipt_path)
    contract=_json(contract_raw); challenge=_json(challenge_raw); receipt=_json(receipt_raw)
    if contract.get('schema')!=SCHEMA or contract.get('status')!='frozen': raise PreflightError('contract not frozen v2')
    if contract.get('execution_mode') not in ('live','offline_fixture'): raise PreflightError('execution mode missing')
    if contract['execution_mode']=='live' and now is not None: raise PreflightError('live mode cannot override time')
    if challenge.get('schema_version')!='eval_contract_challenge_packet_v1' or challenge.get('overall_state')!='ready':
        raise PreflightError('independent ready challenge missing')
    if challenge.get('challenged_contract',{}).get('raw_sha256')!=sha(contract_raw): raise PreflightError('challenge contract hash mismatch')
    if challenge.get('witness',{}).get('mode')!='read_only_offline': raise PreflightError('witness boundary mismatch')
    # Bind actual packet bytes and length. The verification callback separately
    # validates receipt schema/lineage/authority; it must not perform effects.
    challenge_digest=challenge.get('internal_digest')
    if not isinstance(challenge_digest,str) or challenge_digest!=sha(serper.canonical({k:v for k,v in challenge.items() if k!='internal_digest'})):
        raise PreflightError('challenge internal digest mismatch')
    if (receipt.get('packet_raw_sha256')!=sha(challenge_raw) or receipt.get('packet_byte_count')!=len(challenge_raw)
        or receipt.get('packet_internal_digest')!=challenge_digest or receipt.get('state')!='ready'):
        raise PreflightError('challenge receipt mismatch')
    if verify_challenge(challenge_raw,receipt_raw,contract_raw) is not True: raise PreflightError('challenge provenance rejected')
    bindings=contract.get('component_bindings')
    if not isinstance(bindings,dict) or set(bindings)!=set(REQUIRED_COMPONENTS): raise PreflightError('exact component bindings required')
    for path,digest in bindings.items():
        if not isinstance(digest,str) or sha(_component_bytes(ROOT,path))!=digest: raise PreflightError('component hash mismatch')
    observed=challenge.get('context_binding',{}).get('code_bindings_at_inspection')
    if not isinstance(observed,dict): raise PreflightError('challenge code bindings required')
    for path,digest in bindings.items():
        if not isinstance(observed.get(path),dict) or observed[path].get('sha256')!=digest or observed[path].get('size')!=len(_component_bytes(ROOT,path)):
            raise PreflightError('witness code binding mismatch')
    if bindings['dataset-draft-20261029/draft.json']!=DRAFT_SHA or bindings['ui-serper-price-20261029.json']!=PRICE_SHA:
        raise PreflightError('draft or UI observation not original')
    observation=_component_bytes(ROOT,'ui-serper-price-20261029.json')
    draft=_json(_component_bytes(ROOT,'dataset-draft-20261029/draft.json'))
    if verify_ui(observation) is not True: raise PreflightError('UI/account provenance rejected')
    envelope={'known_prior_exposure_micro_usd':721593,'total_cap_micro_usd':40000000,
        'source_budget_micro_usd':5000000,'per_source_reserve_micro_usd':250000,'ui_price_micro_usd':2000,
        'source_attempts':8,'max_source_attempts':18,'max_generation_attempts_including_prior':835,
        'max_countTokens_including_prior':767,'model':'gemini-3.8-flash','location':'global',
        'input_rate_per_million_usd':1.5,'output_rate_per_million_usd':7.5,
        'input_limit':16384,'max_output_tokens':4096,'output_reserve':8192,'retry_policy':'none',
        'uncertain_policy':'stop and retain reserve','ui_price_evidence_sha256':PRICE_SHA,'draft_sha256':DRAFT_SHA}
    for key,value in envelope.items():
        if contract.get(key)!=value: raise PreflightError('user limits or price evidence drift')
    groups=draft.get('groups'); requests=contract.get('source_requests')
    if not isinstance(groups,list) or not isinstance(requests,list) or len(groups)!=8 or len(requests)!=8:
        raise PreflightError('eight groups and requests required')
    if any(not isinstance(r,dict) for r in requests): raise PreflightError('request row must be an object')
    if [r.get('case_id') for r in requests] != [f'case-{i:02}' for i in range(1,9)]:
        raise PreflightError('case ordering or IDs drift')
    if len({r.get('event_group_id') for r in requests})!=8: raise PreflightError('event groups must be distinct')
    built=[]
    for item,group in zip(requests,groups):
        if not isinstance(item,dict) or not isinstance(group,dict): raise PreflightError('bad request/case')
        news=group.get('news_action_draft',{})
        body=item.get('body')
        if (item.get('case_id')!=group.get('case_id') or item.get('event_group_id')!=group.get('event_group_id')
            or item.get('api')!='serper' or item.get('path')!='/news' or body!=news.get('request_body')
            or item.get('relevance_gap')!=news.get('predeclared_relevance_gap')
            or not isinstance(body,dict) or set(body)!={'q','num'} or body.get('num')!=3):
            raise PreflightError('predeclared query drift')
        request=serper.build_request(body['q'],body['num'])
        if item.get('request_sha256')!=sha(request): raise PreflightError('exact request hash mismatch')
        # Evaluate local binding/expiry for ALL calls before any external effect.
        ui_quote.bind_quote(request,observation,expected_sha256=PRICE_SHA,verify_provenance=verify_ui,now=now)
        built.append((item['case_id'],request))
    if not isinstance(ledger,Ledger): raise PreflightError('shared approved Ledger instance required')
    expected_context={'artifact_root':str(ROOT),'ledger_root':str(ledger.root.resolve()),
        'output_dir':str(Path(output_dir).absolute()),'cwd':str(Path.cwd().resolve())}
    if Path(output_dir).parent.resolve()!=Path(output_dir).parent.absolute(): raise PreflightError('symlinked output parent')
    if contract.get('execution_context')!=expected_context or challenge.get('context_binding',{}).get('execution_context')!=expected_context:
        raise PreflightError('execution context path binding mismatch')
    summary=ledger.summary()
    config_raw,config_hash=ledger.db.execute('SELECT contract,contract_hash FROM run WHERE id=1').fetchone()
    if sha(bytes(config_raw))!=config_hash: raise PreflightError('ledger contract integrity failed')
    config=_json(bytes(config_raw))
    if serper.canonical(ledger._contract)!=bytes(config_raw): raise PreflightError('in-memory ledger contract drift')
    configured=_json(_component_bytes(ROOT,'live-ledger-contract-20261029.json'))
    if configured!=config: raise PreflightError('live ledger contract bytes mismatch')
    pricing_hash=sha(_component_bytes(ROOT,'live-pricing-evidence-20261029.json'))
    if any(config.get(k)!=pricing_hash for k in ('model_price_evidence_sha256','count_price_evidence_sha256')):
        raise PreflightError('live pricing evidence hash mismatch')
    expected_config={'prior_micro':721593,'cap_micro':40000000,'prior_generations':79,'prior_counts':11,
        'max_generations':835,'max_counts':767,'max_sources':18,'source_cap_micro':5000000,
        'model':'gemini-3.8-flash','location':'global','input_limit':16384,'output_reserve':8192,
        'max_output_tokens':4096,'input_rate_half_micro':3,'output_rate_half_micro':15}
    if any(config.get(k)!=v for k,v in expected_config.items()): raise PreflightError('ledger contract mismatch')
    if any(summary.get(k)!=v for k,v in {'stopped':0,'exposure_micro':721593,'generation_attempts':79,
                                           'count_attempts':11,'source_attempts':0,'metadata_attempts':0}.items()):
        raise PreflightError('ledger is not fresh or prior lineage changed')
    # The challenge must bind the ledger contract bytes, not only its source.
    if challenge.get('context_binding',{}).get('ledger_contract_sha256')!=sha(serper.canonical(config)):
        raise PreflightError('witness ledger-contract binding mismatch')
    return {'contract_raw':contract_raw,'challenge_raw':challenge_raw,'receipt_raw':receipt_raw,
            'contract':contract,'bindings':bindings,'observation':observation,'requests':built,
            'contract_path':Path(contract_path),'challenge_path':Path(challenge_path),'receipt_path':Path(challenge_receipt_path)}

def execute(contract_path, challenge_path, challenge_receipt_path, output_dir, *, ledger,
            verify_challenge, verify_ui, project_id_provider, token_provider, fixture_http_transport=None, now=None):
    """Explicit opt-in; no external call unless all pre-effect bindings pass.

    Provider/project callback and in-memory token callback are caller-supplied.
    Never serialize their return values. For live mode test transport is forbidden;
    offline fixture mode requires a supplied fake transport and is not live authority.
    """
    ctx=validate(contract_path,challenge_path,challenge_receipt_path,ledger=ledger,output_dir=output_dir,
                 verify_challenge=verify_challenge,verify_ui=verify_ui,now=now)
    mode=ctx['contract']['execution_mode']
    if not callable(project_id_provider) or not callable(token_provider): raise PreflightError('credential callbacks required')
    if mode=='live' and fixture_http_transport is not None: raise PreflightError('injected transport forbidden for live')
    if mode=='offline_fixture' and fixture_http_transport is None: raise PreflightError('offline fixture requires fake transport')
    out=Path(output_dir)
    if out.parent.resolve()!=out.parent.absolute(): raise PreflightError('symlinked output parent')
    out.mkdir(mode=0o700)
    _fd=os.open(out.parent,os.O_RDONLY)
    try: os.fsync(_fd)
    finally: os.close(_fd)
    try:
        _write_once(out/'started.json',{'state':'started','contract_sha256':sha(ctx['contract_raw']),
            'challenge_sha256':sha(ctx['challenge_raw']),'receipt_sha256':sha(ctx['receipt_raw']),
            'mode':mode,'source_ids':[f'source:{c}:serper' for c,_ in ctx['requests']]})
        ledger.db.execute('BEGIN IMMEDIATE')
        if ledger.db.execute("SELECT 1 FROM run_events WHERE event='source_capture_started' LIMIT 1").fetchone():
            raise Stop('source capture already started')
        ledger.db.execute("INSERT INTO run_events(event,reason,at_utc) VALUES ('source_capture_started',?,?)",
            (sha(ctx['contract_raw']),dt.datetime.now(dt.timezone.utc).isoformat()))
        ledger.db.execute('COMMIT')
    except BaseException:
        if ledger.db.in_transaction: ledger.db.execute('ROLLBACK')
        try: ledger.stop('source capture start failed')
        finally: ledger.poisoned=True
        raise
    # No credential retrieval occurs before successful admission/start.
    try:
        project_id=project_id_provider()
        transport=OneShotTransport(project_id,token_provider,http_transport=fixture_http_transport)
        project_id=None
    except BaseException:
        ledger.stop('transport initialization failed')
        raise PreflightError('transport initialization failed') from None
    results=[]
    for case_id,request in ctx['requests']:
        try:
            # No resumed/repeated operation; verify all frozen bytes before each call.
            if (_read(ctx['contract_path'])!=ctx['contract_raw'] or _read(ctx['challenge_path'])!=ctx['challenge_raw']
                or _read(ctx['receipt_path'])!=ctx['receipt_raw'] or any(sha(_component_bytes(ROOT,p))!=h for p,h in ctx['bindings'].items())):
                ledger.stop('source capture evidence drift')
                raise Stop('source capture evidence drift')
            result=ui_quote.execute(ledger,f'source:{case_id}:serper',request,ctx['observation'],
                expected_sha256=PRICE_SHA,verify_provenance=verify_ui,transport=transport,now=now)
            _write_once(out/f'{case_id}.json',{'case_id':case_id,'status':'succeeded','result':result})
            results.append({'case_id':case_id,'status':'succeeded'})
        except BaseException as exc:
            # ledger is authoritative if effect occurred; no retry on any error.
            try: ledger.stop('source capture halted')
            finally: ledger.poisoned=True
            try: _write_once(out/f'{case_id}-stopped.json',{'case_id':case_id,'status':'stopped','error_type':type(exc).__name__})
            except BaseException: pass
            raise
    try:
        _write_once(out/'summary.json',{'status':'completed','source_count':len(results),'ledger':ledger.summary()})
    except BaseException:
        try: ledger.stop('source summary persistence failed')
        finally: ledger.poisoned=True
        raise
    return results
