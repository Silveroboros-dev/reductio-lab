"""Read-only operator provenance checks for cohort builder and runner.

The asserted external origins are relayed or operator-observed, not externally
signed. These checks do not review or adjudicate semantic outputs. No network or
credentials are used here.
"""
from __future__ import annotations
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRED_HASH = '7219ea98341b5dcaa025653cfcc70e68edc593ca8cde5fa2170cdc1f598dd8cd'
UI_HASH = 'b77cd7bd9f5264879dc3b4b7db3cd73f1d2a836995258c4a206a91671e0e8ac9'
REFRESH_UI_HASH = 'bb22abd1885a58a5fd317c5167baa1b70621dae6642343cb6c5fd341ca5ab6ac'
HUMAN_HASH = '953888277ca7de855ae1f514400831a8f69c01816c40b4056c5ad51ef14652ac'
MARKET_HASH = '2f6932c840ecbfc4bc3dac1f52a4f27aeac250f66fe345d0ad371c50be57363b'

def sha(raw): return hashlib.sha256(raw).hexdigest()
def utc(s):
    v=dt.datetime.fromisoformat(s.replace('Z','+00:00'))
    if v.utcoffset()!=dt.timedelta(0): raise ValueError('not UTC')
    return v

def read(root, rel, expected):
    root=Path(root).resolve(); p=root/rel
    if not p.resolve().is_relative_to(root) or p.absolute()!=p.resolve() or not p.is_file(): raise ValueError('unsafe path')
    b=p.read_bytes()
    if sha(b)!=expected: raise ValueError('byte drift')
    return b

class Admission:
    def __init__(self, predecessor, successor, ledger):
        self.pred=Path(predecessor).resolve(); self.out=Path(successor).resolve(); self.ledger=ledger
        raw=(self.pred/'manifest.json').read_bytes()
        if sha(raw)!=PRED_HASH: raise ValueError('predecessor manifest drift')
        m=json.loads(raw)
        self.rows={x['case_id']:x for x in m['cases']}
        if set(self.rows)!={f'case-{n:02}' for n in range(1,9)}: raise ValueError('wrong cases')

    def original(self, row):
        original=self.rows[row['case_id']]
        if any(row.get(k)!=v for k,v in original.items() if k!='input_sha256'): raise ValueError('row lineage drift')
        return original,json.loads(read(self.pred,original['input_path'],original['input_sha256']))

    def verify_human(self, raw, case, row):
        try:
            original,base=self.original(row)
            expected=read(self.pred,original['human_attestation_path'],original['human_attestation_sha256'])
            if raw!=expected or case['task']['case_id']!=row['case_id']: return False
            thesis=[x['text'] for x in case['task']['initial_evidence'] if x.get('id')=='thesis']
            original_thesis=[x['text'] for x in base['task']['initial_evidence'] if x.get('id')=='thesis']
            if len(thesis)!=1 or thesis!=original_thesis: return False
            human=json.loads(raw)
            if row['split']=='test':
                n=int(row['case_id'][-2:])-3
                return (sha(raw)==HUMAN_HASH and human.get('origin')=='user response to request_user_input_async call_37a17a9ce3754dc9bb302466adbbae2a'
                    and human.get('user_response')=='Да, принимаю все шесть' and len(human['test_theses_ru'])==6
                    and 0<=n<6 and thesis[0]==human['test_theses_ru'][n])
            if row['split']!='dev' or human.get('final_verdict')!='approve': return False
            refs={a['path']:a['sha256'] for a in base['attachments']}
            packet=json.loads(read(self.pred,f"human/{row['case_id']}-packet-line.json",refs[f"human/{row['case_id']}-packet-line.json"]))
            master=json.loads(read(self.pred,f"human/{row['case_id']}-master-line.json",refs[f"human/{row['case_id']}-master-line.json"]))
            return (human.get('status')=='approved_exact_proposal' and
                    packet['normalized_claim']['contractible_version']==thesis[0] and
                    human==master.get('canonical_human_approval') and
                    human.get('proposal_digest')==master.get('canonical_proposal',{}).get('proposal_digest') and
                    thesis[0]==master['canonical_proposal']['proposed_normalized_claim']['contractible_version'])
        except (ValueError,KeyError,TypeError,OSError,IndexError): return False

    def verify_capture(self,case,row):
        try:
            original,base=self.original(row)
            # Every unchanged predecessor field and source artifact must survive.
            cand=copy.deepcopy(case); paid=cand.pop('paid_capture')
            news=cand['task']['actions'].pop(); replay=cand['replay'].pop('news')
            added=cand['attachments'][-2:]; cand['attachments']=cand['attachments'][:-2]
            if cand!=base or news.get('id')!='news': return False
            if sha(read(self.pred,'source/targeted-markets.json',MARKET_HASH))!=MARKET_HASH: return False
            receipt=self.ledger.receipt('source:'+row['case_id']+':serper')
            response=receipt['response']; request=receipt['request']
            if receipt.get('state')!='succeeded' or receipt.get('http_status')!=200 or receipt.get('kind')!='source': return False
            if sha(request)!=receipt['request_hash'] or sha(response)!=receipt['response_hash']: return False
            if paid['source_effect_id']!=receipt['id'] or paid['response_sha256']!=receipt['response_hash'] or paid['actual_micro_usd']!=receipt['actual_micro']: return False
            expected_action={'id':'news','description':'Read Serper News results for query: '+base['draft_paid_source']['request_body']['q'],
                'capture_kind':'paid_api','quoted_cost_micro_usd':2000,'source_effect_id':receipt['id'],'captured_at':receipt['completed_at_utc']}
            if news!=expected_action: return False
            if read(self.out,added[0]['path'],added[0]['sha256'])!=response or added[0]['sha256']!=receipt['response_hash']: return False
            expected_quote=UI_HASH if row['case_id']=='case-01' else REFRESH_UI_HASH
            if sha(read(self.out,added[1]['path'],added[1]['sha256']))!=expected_quote or paid['quote_evidence_sha256']!=expected_quote or receipt['quote_evidence_sha']!=expected_quote: return False
            import news_projection
            projection=news_projection.project(response); envelope=json.loads(response)
            rid=envelope.get('requestId') or (envelope.get('billing') or {}).get('requestId')
            expected_paid={'source_effect_id':receipt['id'],'provider_request_id':rid,
                'response_sha256':receipt['response_hash'],'actual_micro_usd':receipt['actual_micro'],
                'quote_evidence_sha256':expected_quote,'news_item_fields':len(projection['fields']),
                'provider_returned_count':projection['provider_returned_count'],'selected_count':projection['selected_count'],'selection':projection['selection']}
            if paid!=expected_paid: return False
            facts=[{'id':identity,'text':text,'source':'Serper News via Orthogonal; '+identity,
                'captured_at':receipt['completed_at_utc'],'content_sha256':receipt['response_hash'],'verbatim_parts':[text]}
                for identity,text in projection['fields']]
            text=f"Provider returned_count={projection['provider_returned_count']}; selected_count={projection['selected_count']}. Selection: first up to 3 in provider order."
            facts.insert(0,{'id':'news:metadata','text':text,'source':'Mechanical projection of captured Serper response',
                'captured_at':receipt['completed_at_utc'],'content_sha256':receipt['response_hash'],'verbatim_parts':[]})
            return replay=={'evidence':facts}
        except (ValueError,KeyError,TypeError,OSError,IndexError,AttributeError): return False

    def verify_quote(self,raw,quote,receipt):
        try:
            expected=UI_HASH if receipt.get('id')=='source:case-01:serper' else REFRESH_UI_HASH
            if receipt.get('id') not in {f'source:case-{i:02}:serper' for i in range(1,9)} or sha(raw)!=expected: return False
            ui=json.loads(raw); req=receipt['request']; request=json.loads(req)
            started=utc(receipt['started_at_utc']); seen=utc(ui['observed_at_utc']); expiry=utc(quote['expires_utc'])
            return (ui['observation'].startswith('Direct visible inspection') and
                (ui['provider'],ui['api'],ui['path'],ui['method'],ui['reported_rate'],ui['scope'])==
                ('orthogonal','serper','/news','POST','$0.002 per call','first page; one non-paginated query with q and num') and
                (request['api'],request['path'],request['query'])==('serper','/news',{}) and
                set(request['body'])=={'q','num'} and request['body']['num']==3 and
                quote['request_sha256']==sha(req) and quote['evidence_sha256']==expected and receipt['quote_evidence_sha']==expected and
                quote['max_micro']==250000 and receipt['quote_micro']==250000 and
                0 <= (started-seen).total_seconds() <= 900 and started<expiry<=seen+dt.timedelta(seconds=900))
        except (ValueError,KeyError,TypeError,AttributeError): return False

def build_cohort(predecessor, successor, ledger, quote_evidence, refresh_quote_evidence):
    """Build after independently settled source captures; no external effects."""
    import sys
    sys.path.insert(0,str(ROOT/'cohort-successor-v2'))
    import builder_v2
    admission=Admission(predecessor,successor,ledger)
    return builder_v2.build(predecessor,successor,ledger,quote_evidence,refresh_quote_evidence,admission.verify_quote,
                         admission.verify_human,admission.verify_capture)
