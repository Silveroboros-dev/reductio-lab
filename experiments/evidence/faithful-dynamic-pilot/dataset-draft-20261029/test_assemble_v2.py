import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import assemble_v2 as assemble

sys.path.insert(0,str(assemble.PILOT/'runner'))
sys.path.insert(0,str(assemble.PILOT/'harness'))
import runner, harness

class OfflineAssemblyTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name).resolve()/'bundle'
 def tearDown(self): self.tmp.cleanup()
 def test_provenance_exact_leaves_and_no_paid_substitution(self):
  predecessor=assemble.sha(assemble.DRAFT.read_bytes());ref=assemble.assemble(self.root)
  self.assertEqual(assemble.sha(assemble.DRAFT.read_bytes()),predecessor)
  m=json.loads((self.root/ref['path']).read_bytes());self.assertEqual(m['schema'],'faithful-dynamic-draft-manifest-v1');self.assertFalse(m['runnable']);self.assertEqual(len(m['cases']),8);self.assertEqual(len(m['pending_sources']),8)
  self.assertEqual([r['split'] for r in m['cases']],['dev','dev']+['test']*6)
  acceptance=json.loads(assemble.ACCEPT.read_bytes())['test_theses_ru']
  for i,row in enumerate(m['cases']):
   raw=runner._read_bound(self.root,row['input_path'],row['input_sha256']);case=json.loads(raw)
   blobs={a['sha256']:runner._read_bound(self.root,a['path'],a['sha256']) for a in case['attachments']}
   harness.prepare_task(case['task'],case['replay'])
   for item in case['task']['initial_evidence']+case['replay']['manual-rules']['evidence']:runner._evidence_bound(item,blobs)
   self.assertEqual([a['id'] for a in case['task']['actions']],['manual-rules'])
   self.assertIsNone(case['task']['actions'][0]['quoted_cost_micro_usd'])
   self.assertIsNone(case['draft_paid_source']['quoted_cost_micro_usd']);self.assertIsNone(case['draft_paid_source']['response'])
   if i>=2:self.assertEqual(case['task']['initial_evidence'][0]['text'],acceptance[i-2])
  fed=json.loads((self.root/m['cases'][0]['input_path']).read_bytes())
  self.assertEqual(fed['source_conflicts'][0]['status'],'unresolved')
 def test_incomplete_manifest_rejected_by_real_preflight(self):
  assemble.assemble(self.root);m=json.loads((self.root/'manifest.json').read_bytes())
  with self.assertRaises(runner.PreflightError):runner.preflight(m,self.root,None,lambda *x:True,lambda *x:True)
 def test_create_only(self):
  assemble.assemble(self.root)
  with self.assertRaises(FileExistsError):assemble.assemble(self.root)
 def test_altered_user_acceptance_rejected_before_output(self):
  changed=json.loads(assemble.ACCEPT.read_bytes());changed['test_theses_ru'][0]+=' extra'
  p=Path(self.tmp.name)/'tampered.json';p.write_text(json.dumps(changed,ensure_ascii=False))
  with patch.object(assemble,'ACCEPT',p):
   with self.assertRaises(ValueError):assemble.assemble(self.root)
  self.assertFalse(self.root.exists())

class NegativeLineageTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name).resolve()
  self.draft=json.loads(assemble.DRAFT.read_bytes());self.packet_lines=assemble.PACKETS.read_bytes().splitlines();self.decision_lines=assemble.DECISIONS.read_bytes().splitlines()
 def tearDown(self):self.tmp.cleanup()
 def build_tampered(self, which):
  provenance=self.draft['groups'][0]['thesis']['provenance']
  packet_i=next(i for i,line in enumerate(self.packet_lines) if assemble.sha(line)==provenance['packet_original_line_sha256'])
  decision_i=next(i for i,line in enumerate(self.decision_lines) if assemble.sha(line)==provenance['approval_original_line_sha256'])
  packet=json.loads(self.packet_lines[packet_i]);decision=json.loads(self.decision_lines[decision_i])
  if which=='packet_digest':packet['source_provenance']['normalization_repair_proposal_digest']='sha256:'+'0'*64
  if which=='decision_digest':
   decision['proposal_digest']='sha256:'+'0'*64;provenance['proposal_digest']=decision['proposal_digest']
  if which=='ordinal':decision['case_ordinal']=19;provenance['case_ordinal']=19
  self.packet_lines[packet_i]=json.dumps(packet,ensure_ascii=False,separators=(',',':')).encode()
  self.decision_lines[decision_i]=json.dumps(decision,ensure_ascii=False,separators=(',',':')).encode()
  provenance['packet_original_line_sha256']=assemble.sha(self.packet_lines[packet_i]);provenance['approval_original_line_sha256']=assemble.sha(self.decision_lines[decision_i])
  packet_raw=b'\n'.join(self.packet_lines)+b'\n';decision_raw=b'\n'.join(self.decision_lines)+b'\n'
  for g in self.draft['groups'][:2]:
   g['thesis']['provenance']['packet_file_sha256']=assemble.sha(packet_raw)
   g['thesis']['provenance']['approval_file_sha256']=assemble.sha(decision_raw)
  paths={}
  for name,raw in [('packets.jsonl',packet_raw),('decisions.jsonl',decision_raw),('draft.json',assemble.encode(self.draft))]:
   path=self.base/name;path.write_bytes(raw);paths[name]=path
  with patch.object(assemble,'PACKETS',paths['packets.jsonl']),patch.object(assemble,'DECISIONS',paths['decisions.jsonl']),patch.object(assemble,'DRAFT',paths['draft.json']):
   with self.assertRaisesRegex(ValueError,'lineage mismatch|source ordinal or proposal differs'):
    assemble.assemble(self.base/'output')
 def test_packet_proposal_digest_change_rejected(self):self.build_tampered('packet_digest')
 def test_decision_and_draft_digest_rebinding_rejected(self):self.build_tampered('decision_digest')
 def test_decision_and_draft_ordinal_rebinding_rejected(self):self.build_tampered('ordinal')

if __name__=='__main__':unittest.main()
