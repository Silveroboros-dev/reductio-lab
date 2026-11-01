"""Create-only OFFLINE draft case assembler; never fetches, spends, or promotes.

Produces a deliberately non-runnable manifest. To add actual paid evidence,
construct a create-only successor rather than modifying these artifacts.
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
PILOT=HERE.parent
WORKTREE=Path('/Users/rk/.codex/worktrees/controller-evidence-integration/fitcheck-core')
DRAFT=HERE/'draft.json'
SOURCE=PILOT/'kalshi_preflight/user_supplied_targeted_kalshi_markets.json'
RECEIPT=PILOT/'kalshi_preflight/user_reported_targeted_capture.json'
ACCEPT=PILOT/'kalshi_preflight/human_test_theses_acceptance.json'
GUIDE=WORKTREE/'docs/label_guide.md'
PACKETS=WORKTREE/'data/review/review_packets_v0.jsonl'
DECISIONS=WORKTREE/'data/review/normalization_holdout_20260827_v1/source_initial_human_decisions_v1.jsonl'
MASTER=WORKTREE/'data/review/normalization_holdout_20260827_v1/master_dispositions_v1.jsonl'
PREDECESSOR=HERE/'assembled-v1/manifest.json'
PREDECESSOR_SHA='831669cc189ea509ea3816f1ea5a356d0f553b9c8bdd10d7dacd1593b82a0feb'
TARGET_SHA='2f6932c840ecbfc4bc3dac1f52a4f27aeac250f66fe345d0ad371c50be57363b'

def sha(raw): return hashlib.sha256(raw).hexdigest()
def encode(obj): return (json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def put(root,name,raw):
    p=root/name; p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write(raw)
    return {'path':name,'sha256':sha(raw)}
def read_json(path):return json.loads(path.read_bytes())
def find_line(path, line_hash):
    rows=[line for line in path.read_bytes().splitlines() if sha(line)==line_hash]
    if len(rows)!=1: raise ValueError('historic line not uniquely bound')
    json.loads(rows[0]); return rows[0]
def ev(identity, text, ref, source):
    if not isinstance(text,str) or not text: raise ValueError('empty evidence not admitted')
    return {'id':identity,'text':text,'source':source,'content_sha256':ref['sha256'],'verbatim_parts':[text]}

def assemble(output_root):
    """New private directory only. Inputs immutable and attached by hash."""
    draft_raw=DRAFT.read_bytes(); draft=json.loads(draft_raw)
    if draft.get('schema')!='faithful-dynamic-draft-v1' or draft.get('status')!='draft_not_frozen_not_runnable': raise ValueError('wrong draft')
    market_raw=SOURCE.read_bytes(); receipt_raw=RECEIPT.read_bytes(); accept_raw=ACCEPT.read_bytes(); guide_raw=GUIDE.read_bytes()
    if sha(market_raw)!=TARGET_SHA or draft['user_relayed_source']['sha256']!=TARGET_SHA or draft['user_relayed_source']['receipt_sha256']!=sha(receipt_raw) or draft['label_guide']['sha256']!=sha(guide_raw): raise ValueError('input drift')
    receipt=json.loads(receipt_raw); accept=json.loads(accept_raw)
    if receipt.get('content_sha256')!=TARGET_SHA or receipt.get('reported_http_status')!=200:raise ValueError('capture receipt mismatch')
    if accept.get('user_response')!='Да, принимаю все шесть' or len(accept.get('test_theses_ru',[]))!=6:raise ValueError('human thesis confirmation mismatch')
    source=json.loads(market_raw); market_map={m['ticker']:m for m in source['markets']}
    groups=draft.get('groups')
    if not isinstance(groups,list) or len(groups)!=8 or len(market_map)!=8 or len({m['event_ticker'] for m in market_map.values()})!=8:raise ValueError('8 distinct event/market groups required')
    if [g.get('split') for g in groups]!=['dev','dev']+['test_candidate']*6:raise ValueError('split mismatch')
    if [g['thesis']['original_text'] for g in groups[2:]]!=accept['test_theses_ru']: raise ValueError('test thesis differs from human confirmation')
    for path, expected in [(PACKETS,groups[0]['thesis']['provenance']['packet_file_sha256']),
                           (DECISIONS,groups[0]['thesis']['provenance']['approval_file_sha256'])]:
        if sha(path.read_bytes())!=expected:raise ValueError('historical provenance file changed')
    master_raw=MASTER.read_bytes(); predecessor_raw=PREDECESSOR.read_bytes()
    if sha(predecessor_raw)!=PREDECESSOR_SHA:raise ValueError('predecessor manifest drift')
    out=Path(output_root); out.mkdir(mode=0o700)  # create-only; never resume or overwrite
    predecessor_ref=put(out,'predecessor/manifest-v1.json',predecessor_raw)
    draft_ref=put(out,'source/draft.json',draft_raw)
    market_ref=put(out,'source/targeted-markets.json',market_raw)
    receipt_ref=put(out,'source/user-reported-capture.json',receipt_raw)
    accept_ref=put(out,'human/test-thesis-acceptance.json',accept_raw)
    guide_ref=put(out,'source/label-guide.md',guide_raw)
    rows=[]; pending=[]
    for i,g in enumerate(groups):
        cid=g['case_id']; tid=g['contract_ids'][0]; m=market_map[tid]
        if g['event_group_id']!=m['event_ticker'] or g['manual_rule_capture']['source_sha256']!=TARGET_SHA: raise ValueError('market identity mismatch')
        if g['news_action_draft']['quoted_cost_micro_usd'] is not None or g['news_action_draft']['response'] is not None:raise ValueError('paid inputs already present in draft')
        common=[market_ref,receipt_ref,guide_ref]
        if i<2:
            p=g['thesis']['provenance']
            if sha(PACKETS.read_bytes())!=p['packet_file_sha256'] or sha(DECISIONS.read_bytes())!=p['approval_file_sha256']:raise ValueError('dev source file mismatch')
            packet_raw=find_line(PACKETS,p['packet_original_line_sha256']);decision_raw=find_line(DECISIONS,p['approval_original_line_sha256'])
            packet=json.loads(packet_raw);decision=json.loads(decision_raw)
            provenance=packet.get('source_provenance',{})
            proposal_digest=p['proposal_digest']
            if (packet['packet_id']!=p['packet_id'] or packet['normalized_claim']['contractible_version']!=g['thesis']['original_text']
                or provenance.get('normalization_repair_proposal_digest')!=proposal_digest
                or decision.get('proposal_digest')!=proposal_digest
                or decision.get('case_ordinal')!=p['case_ordinal']
                or decision.get('run_id')!=provenance.get('normalization_repair_human_decision_run_id')
                or decision.get('status')!='approved_exact_proposal' or decision.get('final_verdict')!='approve'):
                raise ValueError('dev exact human lineage mismatch')
            matches=[]
            for raw_master in master_raw.splitlines():
                master=json.loads(raw_master)
                if master.get('source_case_id')==provenance.get('normalization_repair_parent_source_case_id'):
                    matches.append((master,raw_master))
            if len(matches)!=1:raise ValueError('historical master source identity ambiguous')
            master,master_line=matches[0]
            if (type(master.get('original_case_ordinal')) is not int or master['original_case_ordinal']!=decision['case_ordinal']
                or master.get('canonical_human_approval')!=decision
                or not isinstance(master.get('canonical_proposal'),dict)
                or master['canonical_proposal'].get('proposal_digest')!=proposal_digest
                or master['canonical_proposal'].get('source_case_id')!=master['source_case_id']
                or master['canonical_proposal'].get('proposed_normalized_claim')!=packet['normalized_claim']):
                raise ValueError('dev original source ordinal or proposal differs')
            thesis_ref=put(out,f'human/{cid}-packet-line.json',packet_raw)
            confirmation_ref=put(out,f'human/{cid}-decision-line.json',decision_raw)
            master_ref=put(out,f'human/{cid}-master-line.json',master_line)
            common.extend([thesis_ref,confirmation_ref,master_ref])
            human_source='historical human-approved normalization; advisory scope; no current session attestation'
        else:
            thesis_ref=accept_ref; confirmation_ref=accept_ref;common.append(accept_ref)
            human_source='user-approved conditional thesis wording, original Russian; no truth or pair-label attestation'
        initial=[ev('thesis',g['thesis']['original_text'],thesis_ref,human_source),
                 ev('market-id',tid,market_ref,'user-relayed Kalshi response; origin not independently verified'),
                 ev('market-title',m['title'],market_ref,'user-relayed Kalshi response; origin not independently verified'),
                 ev('label-guide',guide_raw.decode(),guide_ref,'active FitCheck label guide')]
        if [g['initial_evidence'][1]['text'],g['initial_evidence'][2]['text']] != [tid,m['title']]:raise ValueError('initial candidate altered')
        fields=g['manual_rule_capture']['replay_evidence']
        expected_fields=[('primary-rule','rules_primary')]+([('secondary-rule','rules_secondary')] if m.get('rules_secondary') else [])
        if [(v['id'],v['source_field']) for v in fields]!=expected_fields or any(v['text']!=m[v['source_field']] for v in fields):raise ValueError('rule source mismatch')
        replay=[ev(v['id'],v['text'],market_ref,'user-relayed Kalshi field; source completeness not established') for v in fields]
        manual={'id':'manual-rules','description':g['manual_rule_capture']['description'],'capture_kind':'manual_capture','quoted_cost_micro_usd':None,
                'manual_receipt_path':receipt_ref['path'],'manual_receipt_sha256':receipt_ref['sha256']}
        task={'case_id':cid,'question':g['question'],'contract_ids':[tid],'allowed_labels':g['allowed_labels'],'initial_evidence':initial,'actions':[manual]}
        case={'task':task,'replay':{'manual-rules':{'evidence':replay}},'attachments':common,
              'source_conflicts':copy.deepcopy(g['source_conflicts']),
              'draft_paid_source':copy.deepcopy(g['news_action_draft']),
              'manual_source_limitations':{'secondary_field_empty':not bool(m.get('rules_secondary')),'completeness':'not established','origin':'user-relayed Grok claim; not independently verified'}}
        case_ref=put(out,f'cases/{cid}.json',encode(case))
        rows.append({'case_id':cid,'event_group_id':m['event_ticker'],'split':'dev' if i<2 else 'test','input_path':case_ref['path'],'input_sha256':case_ref['sha256'],
                     'human_attestation_path':confirmation_ref['path'],'human_attestation_sha256':confirmation_ref['sha256']})
        pending.append({'case_id':cid,'required':'actual Orthogonal response+settled ledger receipt+account-specific fixed quote+request identity+source extraction','predeclared_query':g['news_action_draft']['request_body'],'price':'unknown','response':'missing'})
    result={'schema':'faithful-dynamic-draft-manifest-v1','status':'blocked_missing_paid_source_capture_and_quote',
            'runnable':False,'draft_predecessor':draft_ref,'predecessor_manifest_v1':predecessor_ref,'master_source_file_sha256':sha(master_raw),'source_receipt':receipt_ref,'cases':rows,'pending_sources':pending,
            'limitations':['A schema intentionally rejected by runnable preflight prevents a manual-only downgrade.',
              'Six test wordings approved, not predictions or pair adjudications; two dev approvals are historical advisory normalization only.',
              'Kalshi transport is user-relayed; Fed rule conflict unresolved; price data capture time is not independently established.',
              'No source price, news response, human goldens, or final evaluation was invented.']}
    result_ref=put(out,'manifest.json',encode(result))
    return result_ref

if __name__=='__main__':
    print(json.dumps(assemble(HERE/'assembled-v2'),ensure_ascii=False))
