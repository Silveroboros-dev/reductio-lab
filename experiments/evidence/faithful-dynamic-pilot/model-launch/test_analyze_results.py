import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import analyze_results as m

def save(path,obj):path.write_text(json.dumps(obj))
def test_distinguishes_unfinished_failure_and_preliminary_answers(tmp_path):
    save(tmp_path/'schedule.json',[{'case_id':'x','arm':'A'},{'case_id':'x','arm':'B'},{'case_id':'x','arm':'C'}])
    save(tmp_path/'00.json',{'slot':0,'case_id':'x','arm':'A','semantic_status':'proposal_unreviewed','outcome':{'status':'completed','model_calls':2,'result':{'answers':[{'contract_id':'T','label':'direct'}]}}})
    save(tmp_path/'01.json',{'slot':1,'case_id':'x','arm':'B','status':'technical_failure','error_type':'ProtocolError','partial_trace':[{'event':'generation_returned','stage':'source_selection','result':{'action':'action','action_id':'news'}}]})
    save(tmp_path/'02-started.json',{'state':'started'})
    x=m.analyze(tmp_path)
    assert x['saved_slots']==2 and x['rows'][0]['answers'][0]['label']=='direct'
    assert x['rows'][1]['model_source_proposals'][0]['action']=='action'
    assert x['rows'][2]['status']=='in_progress' and x['final_ledger_summary'] is None

def test_reads_c_controller_source_and_proposed_answer():
    x=m.row({'slot':3,'case_id':'x','arm':'C','semantic_status':'proposal_unreviewed','outcome':{'status':'proposal','calls':4,'events':[{'event':'source_replayed','action_id':'news'}],'proposed_answers':[{'contract_id':'T','label':'weak_proxy'}]}})
    assert x['source_selected']=='news' and x['answers'][0]['label']=='weak_proxy' and x['model_calls_recorded']==4
