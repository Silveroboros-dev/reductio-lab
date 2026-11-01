"""Read-only projection of untouched case02–04 from interrupted p0 inputs."""
import copy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for d in ('forecast-p0-launch-v1','forecast-p0-remaining-v1'):
 sys.path.insert(0,str(ROOT/d))
import p0_launcher as p,case_binding,dispatch as prior

P0_SHA='cc1b4469ea42b3a9052743023404178e72776b8a05a06825fe9e477b739cc524'
EXPECTED=('case-02','case-03','case-04')
class Error(ValueError):pass

def build(clock):
 """Exact subset from the *already saved* original, never regenerate case01."""
 _,cr,challenge,receipt,original=prior.verify(P0_SHA)
 saved_root=ROOT/'forecast-p0-results-20261029-01'
 saved_raw=p._read(saved_root/'p0-bundle.json');saved=p._json(saved_raw)
 if saved!=original:raise Error('original p0 bundle differs from frozen inputs')
 start=p._json(p._read(saved_root/'started.json'))
 if (start.get('contract_sha256')!=P0_SHA or start.get('challenge_sha256')!=p.o.sha(challenge) or
  start.get('receipt_sha256')!=p.o.sha(receipt)):raise Error('original p0 start binding mismatch')
 first_input=p._json(p._read(saved_root/'00-p0-input.json'))
 if first_input!=original['prepared'][0]:raise Error('case01 initial input mismatch')
 first=p._json(p._read(saved_root/'00-p0-c.json'))
 if first.get('status')!='proposal' or not isinstance(first.get('result'),dict):raise Error('case01 C partial record not as expected')
 # These artifacts were never created by the interrupted runner. This check is
 # necessary but not proof of no model effects; accounting successor must audit
 # the effect journal independently before authorizing these case IDs.
 for i in range(1,4):
  if any(saved_root.glob(f'{i:02d}-p0-*.json')):raise Error('remaining case has prior output')
 if any((saved_root/f'00-p0-{suffix}.json').exists() for suffix in ('b','frozen','receipt')):
  raise Error('case01 is no longer partial as expected')
 if tuple(x['case']['case_id'] for x in original['prepared'])!=('case-01',)+EXPECTED:
  raise Error('original case order mismatch')
 remaining={'schema':original['schema'],'common_as_of_utc':original['common_as_of_utc'],
  'bindings':copy.deepcopy(original['bindings'][1:]),'prepared':copy.deepcopy(original['prepared'][1:])}
 if tuple(x['case']['case_id'] for x in remaining['prepared'])!=EXPECTED:raise Error('remaining identities mismatch')
 return {'bundle':remaining,'bundle_sha256':p.o.sha(p.o.canonical(remaining)),
  'original_contract_sha256':P0_SHA,'original_bundle_sha256':p.o.sha(saved_raw),
  'original_started_sha256':p.o.sha(p._read(saved_root/'started.json')),
  'partial_case01_c_sha256':p.o.sha(p._read(saved_root/'00-p0-c.json')),
  'case01_status':'C saved; B/pair unavailable; do not retry',
  'qualification':'No independent conclusion about remaining effect journal until successor audit.'}
