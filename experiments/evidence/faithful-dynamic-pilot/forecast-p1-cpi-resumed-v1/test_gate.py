import copy,unittest
import gate

class Tests(unittest.TestCase):
 def setUp(self):
  self.p=gate.verify_p0();case=self.p['prepared']['case']
  self.news=[{'id':'synthetic-pce','kind':'news','text':'Hypothetical new PCE value; synthetic fixture only.','source':'synthetic test fixture',
   'published_at_utc':'2026-10-29T12:30:00Z','available_at_utc':'2026-10-29T12:30:01Z','captured_at_utc':'2026-10-29T12:30:02Z'}]
  self.status={'contract_id':gate.TICKER,'state':'active','result':'','rules_primary':case['rules_primary'],'rules_secondary':case['rules_secondary'],
   'observed_at_utc':'2026-10-29T12:30:03Z','captured_at_utc':'2026-10-29T12:30:04Z','quote':'SECRET-NOT-FOR-MODEL'}
  self.t='2026-10-29T12:30:05Z'
 def prep(self,news=None,status=None,verify_news=lambda *a:True,verify_status=lambda *a:True,t=None):
  return gate.prepare(self.news if news is None else news,self.status if status is None else status,t1=t or self.t,verify_news=verify_news,verify_status=verify_status)
 def test_real_receipts_without_network(self):
  self.assertEqual(self.p['receipt']['schema'],'resumed-original-p0-receipt-v1')
  self.assertTrue(self.p['p0_frozen']['comparison_eligible'])
  self.assertEqual(self.p['receipt']['durable_before_utc'],gate.DURABLE)
 def test_four_matched_conditions_own_priors_no_status_leak(self):
  a=self.prep();self.assertEqual(a['status'],'ready');tasks=a['bundle']['tasks']
  self.assertEqual(set(tasks),{'c_news','b_news','c_no_news','b_no_news'})
  for arm in ('c','b'):
   self.assertEqual(tasks[arm+'_news']['prior_forecast'],self.p['p0_frozen'][arm]['result'])
   self.assertEqual(tasks[arm+'_no_news']['prior_forecast'],self.p['p0_frozen'][arm]['result'])
   self.assertNotIn('synthetic-pce',{e['id'] for e in tasks[arm+'_no_news']['evidence']})
   self.assertIn('synthetic-pce',{e['id'] for e in tasks[arm+'_news']['evidence']})
  self.assertNotIn('SECRET-NOT-FOR-MODEL',str(tasks))
  self.assertEqual(a['p0_receipt_schema'],'resumed-original-p0-receipt-v1')
 def test_missing_news_and_status_pending(self):
  self.assertEqual(gate.prepare([],None,t1=self.t,verify_news=None,verify_status=None)['status'],'pending')
  self.assertEqual(gate.prepare(self.news,None,t1=self.t,verify_news=None,verify_status=None)['status'],'pending')
 def test_prep_rejects_pre_p0_or_unknown_news_timestamp(self):
  for v in ('2026-10-29T11:51:50.322164+00:00',None,'2026-10-29T11:51:50Z'):
   n=copy.deepcopy(self.news);n[0]['published_at_utc']=v;self.assertEqual(self.prep(news=n)['status'],'pending')
 def test_admission_requires_independent_review(self):
  self.assertEqual(self.prep(verify_news=lambda *a:False)['status'],'pending')
  self.assertEqual(self.prep(verify_status=lambda *a:False)['status'],'pending')
  with self.assertRaises(gate.Error):self.prep(verify_news=None)
 def test_requires_open_same_rule_and_fresh_post_news_status(self):
  for mutation in ({'state':'closed'},{'result':'yes'},{'rules_primary':'changed'},{'observed_at_utc':'2026-10-29T12:30:01Z'},{'captured_at_utc':'2026-10-29T12:25:00Z'}):
   status={**self.status,**mutation};self.assertEqual(self.prep(status=status)['status'],'pending')
  self.assertEqual(self.prep(t='2026-10-29T12:35:05Z')['status'],'pending')
 def test_nonempty_event_before_close_required(self):
  self.assertEqual(self.prep(t='2026-11-10T13:29:00Z')['status'],'pending')
if __name__=='__main__':unittest.main()
