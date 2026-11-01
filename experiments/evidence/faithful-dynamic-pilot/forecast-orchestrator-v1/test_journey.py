import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import journey, orchestrator as o
from test_orchestrator import case, news, mkresult, yes

def task():
    return {'case_id':'one','thought':'A carefully scoped human thought about one event','thought_origin':'user_exact',
      'as_of_utc':'2026-10-29T09:50:00Z',
      'evidence':[{'id':'source1','text':'some independent source','source':'Source',
        'available_at_utc':'2026-10-29T09:40:00Z','captured_at_utc':'2026-10-29T09:41:00Z'}],
      'market_leads':[{'market_id':'ticker-1','title':'Unseen market title',
         'source':'venue snapshot','captured_at_utc':'2026-10-29T09:45:00Z'}]}

def direction(arm,with_market=False):
    return {'candidate':'candidate '+arm,'connection':'related conditional hypothesis','mechanism':None,
       'observable':'a bounded observation','horizon':None,'falsifier':'opposite evidence','alternatives':[],
       'counterevidence':[],'suggested_market_ids':['ticker-1'] if with_market else [],'citations':['input:thought']}

class JourneyTest(unittest.TestCase):
    def setUp(self):self.log=[];self.generations=[]
    def record(self,name,value):self.log.append((name,copy.deepcopy(value)))
    def factory(self,phase,condition,arm):
        def gen(stage,payload):
            self.generations.append((phase,condition,arm,stage,copy.deepcopy(payload)))
            if arm=='b':self.assertNotIn('candidate c',str(payload))
            if phase=='exploration' and condition=='seed':
                self.assertNotIn('Unseen market title',str(payload));self.assertNotIn('ticker-1',str(payload))
            if stage=='explore_selection':return {'selected_ids':['input:thought']}
            if stage=='explore_inference':return {'conclusion':'a cautious inference'}
            if stage=='explore_halter':return {'sufficient':True}
            if stage in ('explore_formatter','explore_baseline_initial','explore_baseline_recheck'):
                return {'directions':[direction(arm)],'unknown_reason':None}
            if stage=='explore_post_market':
                parent=payload['seed_directions'][0]['seed_sha256']
                return {'post_market_directions':[{'parent_seed_sha256':parent,'direction':direction(arm,True)}],'unknown_reason':None}
            if stage=='selection':return {'alternatives':[['rule:primary']]}
            if stage=='inference':return {'conclusion':'a cautious inference'}
            if stage=='halter':return {'sufficient':True}
            if stage=='value':return {'score':0.8}
            if stage in ('formatter','baseline_initial','baseline_recheck'):return mkresult(arm)
            self.fail('unexpected stage '+stage)
        return gen
    def prepare(self):return journey.prepare_exploration(task(),verify_thought=yes,verify_sources=yes,verify_leads=yes)
    def run_exploration(self,p):return journey.run_exploration(p,generator_factory=self.factory,record=self.record,clock=lambda:'2026-10-29T09:55:00Z')
    def make_decision(self,result):
        c=case();return {'case_id':'one','exploration_result_sha256':o.sha(o.canonical(result)),
          'thesis_sha256':o.sha(c['thesis'].encode()),'market_id':c['contract_id'],
          'decided_at_utc':'2026-10-29T09:58:00Z','origin':'synthetic user decision'}
    def test_full_offline_journey_proposals_human_p0_p1_and_cards(self):
        prepared=self.prepare();out=self.run_exploration(prepared)
        names=[name for name,_ in self.log]
        self.assertLess(names.index('exploration-c-seed'),names.index('exploration-c-post-market'))
        self.assertLess(names.index('exploration-b-seed'),names.index('exploration-c-post-market'))
        self.assertTrue(out['no_human_decision_recorded'])
        self.assertEqual(out['post_market']['c']['total_calls'],5)
        self.assertEqual(out['post_market']['b']['total_calls'],5)
        decision=self.make_decision(out)
        binding=journey.bind_human_decision(prepared,out,case(),decision,verify_decision=yes)
        self.assertEqual(binding['decision_sha256'],o.sha(o.canonical(decision)))
        pc=o.prepare_case(case(),verify_human=yes,verify_rules=yes)
        p0=o.run_p0(pc,generator_factory=self.factory,record=self.record,clock=lambda:'2026-10-29T10:30:00Z')
        bundle=o.prepare_p1(pc,p0,news(),t1='2026-10-29T11:30:00Z',verify_p0=yes,verify_intervention=yes,verify_unresolved=yes)
        p1=o.run_p1(bundle,expected_bundle_sha256=o.sha(o.canonical(bundle)),verify_bundle=yes,generator_factory=self.factory,record=self.record)
        self.assertEqual(p1['results']['news']['c']['result']['probability_yes'],0.4)
        self.assertEqual(p1['results']['news']['b']['result']['probability_yes'],0.6)
        ids=iter(['a','b','c']);cards,private=journey.blindable_seed_cards(prepared,out,id_factory=lambda:next(ids),shuffle=lambda x:None)
        self.assertEqual(len(cards),3);self.assertEqual(len(private),3)
        self.assertNotIn('Unseen market title',str(cards));self.assertNotIn('ticker-1',str(cards))
    def test_unverified_input_or_market_prevents_model_execution(self):
        for key in ('verify_thought','verify_sources','verify_leads'):
            args={'verify_thought':yes,'verify_sources':yes,'verify_leads':yes};args[key]=lambda x:False
            with self.subTest(key=key),self.assertRaises(o.EligibilityError):journey.prepare_exploration(task(),**args)
        self.assertEqual(self.generations,[])
    def test_market_title_in_seed_fails_before_generation(self):
        t=task();t['thought']='This is about Unseen market title'
        with self.assertRaises(Exception):journey.prepare_exploration(t,verify_thought=yes,verify_sources=yes,verify_leads=yes)
        self.assertEqual(self.generations,[])
    def test_human_decision_is_separate_and_content_bound(self):
        p=self.prepare();r=self.run_exploration(p);d=self.make_decision(r)
        with self.assertRaises(o.EligibilityError):journey.bind_human_decision(p,r,case(),d,verify_decision=lambda *x:False)
        for field,value in [('thesis_sha256','a'*64),('market_id','other'),('decided_at_utc','2026-10-29T09:53:00Z')]:
            x=copy.deepcopy(d);x[field]=value
            with self.subTest(field=field),self.assertRaises(o.EligibilityError):journey.bind_human_decision(p,r,case(),x,verify_decision=yes)
    def test_seed_record_failure_prevents_other_effects(self):
        p=self.prepare()
        def record(name,value):
            if name=='exploration-c-seed':raise OSError('disk')
        with self.assertRaises(OSError):journey.run_exploration(p,generator_factory=self.factory,record=record,clock=lambda:'2026-10-29T09:55:00Z')
        self.assertTrue(all(item[2]=='c' for item in self.generations))

if __name__=='__main__':unittest.main()
