import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import orchestrator as o

def case():
    thesis='A testable accepted thesis'
    return {'case_id':'one','event_group_id':'group-1','thesis':thesis,'contract_id':'ticker-1',
      'rules_primary':'The event occurs before the deadline.','rules_secondary':'Only published results count.',
      'rules_capture_sha256':'a'*64,'rules_capture_source':'synthetic source','rules_captured_at_utc':'2026-10-29T09:00:00Z',
      'close_time_utc':'2026-11-04T00:00:00Z','p0_as_of_utc':'2026-10-29T10:00:00Z',
      'human_approval':{'thesis_sha256':o.sha(thesis.encode()),'approval_recorded_at_utc':'2026-10-29T09:30:00Z'},
      'baseline_evidence':[{'id':'context:1','kind':'context','text':'prior facts','source':'source A',
        'available_at_utc':'2026-10-29T09:40:00Z','captured_at_utc':'2026-10-29T09:41:00Z'}]}

def news():return [{'id':'news:1','kind':'news','text':'NEW FACT','source':'primary',
 'published_at_utc':'2026-10-29T11:00:00Z','available_at_utc':'2026-10-29T11:01:00Z','captured_at_utc':'2026-10-29T11:02:00Z'}]

def yes(*args):return True
def mkresult(arm):return {'probability_yes':0.4 if arm=='c' else 0.6,
    'explanation':'C-SECRET' if arm=='c' else 'B-own',
    'citations':['rule:primary'],'assumptions':['fallible'],'counterevidence':['unknown']}

class OrchestratorTest(unittest.TestCase):
    def setUp(self):self.log=[];self.operations=[]
    def record(self,name,value):self.log.append((name,copy.deepcopy(value)))
    def factory(self,phase,condition,arm):
        self.operations.append((phase,condition,arm))
        def generate(stage,payload):
            if arm=='b': self.assertNotIn('C-SECRET',str(payload))
            if stage=='selection':return {'alternatives':[['rule:primary']]}
            if stage=='inference':return {'conclusion':'A cautious conclusion.'}
            if stage=='halter':return {'sufficient':True}
            if stage=='value':return {'score':0.8}
            if stage in ('baseline_initial','baseline_recheck','formatter'):return mkresult(arm)
            self.fail('unexpected stage '+stage)
        return generate
    def prepared(self):return o.prepare_case(case(),verify_human=yes,verify_rules=yes)
    def p0(self,p):return o.run_p0(p,generator_factory=self.factory,record=self.record,clock=lambda:'2026-10-29T10:30:00Z')
    def bundle(self,p,z,items=None):return o.prepare_p1(p,z,news() if items is None else items,t1='2026-10-29T11:30:00Z',verify_p0=yes,verify_intervention=yes,verify_unresolved=yes)
    def test_complete_separate_priors_and_blinded_cards(self):
        p=self.prepared();z=self.p0(p);b=self.bundle(p,z)
        self.assertEqual(b['tasks']['c_news']['prior_forecast']['explanation'],'C-SECRET')
        self.assertEqual(b['tasks']['b_news']['prior_forecast']['explanation'],'B-own')
        self.assertNotIn('NEW FACT',str(b['tasks']['c_no_news']))
        self.assertNotIn('NEW FACT',str(b['tasks']['b_no_news']))
        p1=o.run_p1(b,expected_bundle_sha256=o.sha(o.canonical(b)),verify_bundle=yes,generator_factory=self.factory,record=self.record)
        self.assertEqual(len(p1['results']),2)
        self.assertEqual(self.operations,[('p0','no_news','c'),('p0','no_news','b'),('p1','no_news','c'),('p1','no_news','b'),('p1','news','c'),('p1','news','b')])
        ids=iter(['a','b','c','d','e','f']);cards,mapping=o.review_cards(p,b,p1,id_factory=lambda:next(ids),shuffle=lambda x:None)
        self.assertEqual(len(cards),6);self.assertEqual(len(mapping),6)
        self.assertTrue(all('arm' not in card and 'condition' not in card for card in cards))
        self.assertTrue(all('NEW FACT' not in str(card['evidence']) for card in cards[:3]))
    def test_no_user_approval_or_rules_no_run(self):
        with self.assertRaises(o.EligibilityError):o.prepare_case(case(),verify_human=lambda x:False,verify_rules=yes)
        with self.assertRaises(o.EligibilityError):o.prepare_case(case(),verify_human=yes,verify_rules=lambda x:False)
        self.assertEqual(self.log,[])
    def test_user_approval_binds_exact_meaning(self):
        x=case();x['thesis']+=' changed'
        with self.assertRaises(o.EligibilityError):o.prepare_case(x,verify_human=yes,verify_rules=yes)
    def test_late_baseline_news_or_snapshot_rejected(self):
        for mutation in ('late','news','rules'):
            x=case()
            if mutation=='late':x['baseline_evidence'][0]['captured_at_utc']='2026-10-29T10:30:00Z'
            if mutation=='news':x['baseline_evidence'][0]['kind']='news'
            if mutation=='rules':x['rules_captured_at_utc']='2026-10-29T10:30:00Z'
            with self.subTest(mutation=mutation),self.assertRaises(o.EligibilityError):o.prepare_case(x,verify_human=yes,verify_rules=yes)
    def test_news_not_genuinely_post_p0_rejected(self):
        p=self.prepared();z=self.p0(p);n=news();n[0]['published_at_utc']='2026-10-29T10:00:00Z'
        with self.assertRaises(o.EligibilityError):self.bundle(p,z,n)
    def test_unknown_date_and_late_capture_rejected(self):
        p=self.prepared();z=self.p0(p)
        for field,val in [('published_at_utc',None),('captured_at_utc','2026-10-29T12:00:00Z')]:
            n=news();n[0][field]=val
            with self.subTest(field=field),self.assertRaises(o.EligibilityError):self.bundle(p,z,n)
    def test_empty_news_and_unresolved_failure_rejected(self):
        p=self.prepared();z=self.p0(p)
        with self.assertRaises(o.EligibilityError):self.bundle(p,z,[])
        with self.assertRaises(o.EligibilityError):o.prepare_p1(p,z,news(),t1='2026-10-29T11:30:00Z',verify_p0=yes,verify_intervention=yes,verify_unresolved=lambda *x:False)
    def test_identical_news_does_not_count_as_new_information(self):
        p=self.prepared();z=self.p0(p)
        for field,value in [('id','context:1'),('text','prior facts')]:
            n=news();n[0][field]=value
            with self.subTest(field=field),self.assertRaises(o.EligibilityError):self.bundle(p,z,n)
    def test_post_close_and_swapped_prior_rejected(self):
        p=self.prepared();z=self.p0(p)
        with self.assertRaises(o.EligibilityError):o.prepare_p1(p,z,news(),t1='2026-11-04T00:00:00Z',verify_p0=yes,verify_intervention=yes,verify_unresolved=yes)
        z['case_sha256']='b'*64
        with self.assertRaises(o.EligibilityError):self.bundle(p,z)
    def test_input_binding_and_record_failure_stop(self):
        p=self.prepared();p['task']['question']='altered'
        with self.assertRaises(o.EligibilityError):self.p0(p)
        self.assertEqual(self.operations,[])
        p=self.prepared()
        def fail(name,data):raise OSError('disk')
        with self.assertRaises(OSError):o.run_p0(p,generator_factory=self.factory,record=fail,clock=lambda:'2026-10-29T10:30:00Z')
        self.assertEqual(self.operations,[])
    def test_changed_p1_bundle_or_verifier_rejected(self):
        p=self.prepared();z=self.p0(p);b=self.bundle(p,z);expected=o.sha(o.canonical(b))
        changed=copy.deepcopy(b);changed['tasks']['b_news']['question']='other'
        with self.assertRaises(o.EligibilityError):o.run_p1(changed,expected_bundle_sha256=expected,verify_bundle=yes,generator_factory=self.factory,record=self.record)
        with self.assertRaises(o.EligibilityError):o.run_p1(b,expected_bundle_sha256=expected,verify_bundle=lambda b:False,generator_factory=self.factory,record=self.record)

if __name__=='__main__':unittest.main()
