"""Offline admission checks; all ledger and artifacts here are synthetic."""
import json
from pathlib import Path
from unittest.mock import patch
import historical_seed as h

class DB:
 def execute(self,sql):
  class Result:
   def __init__(self, rows): self.rows=rows
   def fetchall(self): return self.rows
  if 'run_events' in sql: return Result([(h.CONTRACT_SHA,)])
  if 'effects' in sql:
   rows=[]
   for i in range(1,5):
    for arm in ('c','b'):
     key=f'seed:case-{i:02d}:{arm}:01'
     rows.extend([('count:'+key,'count','succeeded',0),('generation:'+key,'generation','succeeded',10)])
   return Result(rows)
  raise AssertionError(sql)
class Base:
 def __init__(self,*a): self.db=DB()
 def close(self): pass
 def summary(self): return {'stopped':0,'exposure_micro':1239670,'generation_attempts':208,'count_attempts':140,'source_attempts':5,'metadata_attempts':0,'metadata_retained_micro':0}

def test_complete_and_incomplete(tmp_path):
 import sys
 sys.path.insert(0,str(h.ROOT/'forecast-budget-v1'))
 sys.path.insert(0,str(h.ROOT/'source-successor'))
 import forecast_ledger,reopen
 def dump(name,obj): (tmp_path/name).write_text(json.dumps(obj))
 rows=[{'case_id':f'case-{i:02d}','split':'development' if i==1 else 'diagnostic','task_sha256':str(i)} for i in range(1,5)]
 source={'binding':'source'};contract={'source_binding':source,'execution_context':{'output_root':str(tmp_path),'ledger_root':'unused'},'task_bindings':rows}
 ctx={'contract':contract,'challenge_raw':b'challenge','receipt_raw':b'receipt'}
 dump('started.json',{'contract_sha256':h.CONTRACT_SHA,'challenge_sha256':h.launcher.sha(b'challenge'),'receipt_sha256':h.launcher.sha(b'receipt'),'case_ids':[x['case_id'] for x in rows]})
 pairs=[]
 for i,row in enumerate(rows):
  result={'calls':1};pair=dict(row,c=result,b=result);pairs.append(pair)
  dump(f'{i:02d}-c.json',result);dump(f'{i:02d}-b.json',result);dump(f'{i:02d}-pair.json',pair)
 summary={'requested_cases':4,'attempted_cases':4,'not_attempted_cases':0,'stop_index':None,'status':'seed_proposals_only','post_market':'not started','review':'not human-adjudicated','results':pairs,'ledger':dict(Base().summary(),source_attempts=13,previous_source_attempts=8)}
 dump('summary.json',summary)
 with patch.object(h.launcher,'verify',return_value=ctx),patch.object(h.historical_five,'verify',return_value=source),patch.object(forecast_ledger,'_check_resumable'),patch.object(reopen,'_ReadOnlyBase',Base):
  binding=h.verify()
  assert binding['model_generation_count']==8 and binding['model_usage_micro']==80
  summary['attempted_cases']=3;dump('summary.json',summary)
  try:h.verify()
  except h.launcher.Error:pass
  else:raise AssertionError('incomplete run admitted')
