"""Read-only projection of never-started 03–04 after two stopped p0 phases."""
import copy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
for d in ('forecast-p0-final-two-v1','forecast-p0-remaining-v1','forecast-p0-launch-v1'):
 sys.path.insert(0,str(ROOT/d))
import p0_launcher as p,dispatch_remaining as prior

P0_SHA='fb9781f15f81baa728902ba9a60add0ea6ff94db3f66e99f5058f287cc6a5f4d'
EXPECTED=('case-03','case-04')
class Error(ValueError):pass

def build():
 _,cr,challenge,receipt,original=prior.verify(P0_SHA)
 root=ROOT/'forecast-p0-remaining-results-20261029-01'
 saved_raw=p._read(root/'p0-bundle.json');saved=p._json(saved_raw)
 if saved!=original:raise Error('three-case input bundle drift')
 start=p._json(p._read(root/'started.json'))
 if (start.get('contract_sha256')!=P0_SHA or start.get('challenge_sha256')!=p.o.sha(challenge) or
  start.get('receipt_sha256')!=p.o.sha(receipt)):raise Error('three-case start binding mismatch')
 if p._json(p._read(root/'00-p0-input.json'))!=original['prepared'][0]:raise Error('case02 original input drift')
 first=p._json(p._read(root/'00-p0-c.json'))
 if first.get('status')!='proposal' or not isinstance(first.get('result'),dict):raise Error('case02 C partial record missing')
 for i in (1,2):
  if any(root.glob(f'{i:02d}-p0-*.json')):raise Error('candidate case has prior output')
 if any((root/f'00-p0-{suffix}.json').exists() for suffix in ('b','frozen','receipt')):
  raise Error('case02 is no longer partial as expected')
 if tuple(x['case']['case_id'] for x in original['prepared'])!=('case-02',)+EXPECTED:raise Error('case order mismatch')
 bundle={'schema':original['schema'],'common_as_of_utc':original['common_as_of_utc'],
  'bindings':copy.deepcopy(original['bindings'][1:]),'prepared':copy.deepcopy(original['prepared'][1:])}
 return {'bundle':bundle,'bundle_sha256':p.o.sha(p.o.canonical(bundle)),
  'original_contract_sha256':P0_SHA,'original_bundle_sha256':p.o.sha(saved_raw),
  'original_started_sha256':p.o.sha(p._read(root/'started.json')),
  'partial_case02_c_sha256':p.o.sha(p._read(root/'00-p0-c.json')),
  'case02_status':'C saved; B/pair unavailable; do not retry',
  'qualification':'No conclusion about remaining effect journal until successor accounting audit.'}
