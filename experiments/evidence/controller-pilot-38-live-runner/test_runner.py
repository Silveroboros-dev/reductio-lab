import ast
import json
import tempfile
import unittest
from pathlib import Path

import runner


def decision(action='stop', action_id=None, answer='unknown', comparison=None):
    value = {'action': action, 'action_id': action_id, 'rationale': 'reason',
             'expected_result': 'value' if action == 'query' else '', 'answer': answer,
             'stop_reason': 'done' if action == 'stop' else '', 'uncertainty': ''}
    if comparison is not None: value['observed_vs_expected'] = comparison
    return value


def canary_values():
    return [decision(), {'issue': True, 'critique': 'query the report'},
            decision('query','synthetic-report', ''), decision(answer='27',comparison='matched')]


def envelope(value, model='gemini-3.8-flash', usage=None):
    return json.dumps({'modelVersion': model,
        'usageMetadata': usage if usage is not None else {'promptTokenCount':100, 'totalTokenCount':200},
        'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(value)}]}}]}).encode()


class FakeProvider:
    def __init__(self, items, model='gemini-3.8-flash'):
        self.items, self.model = list(items), model
        self.prompts, self.calls = [], []
    def request(self, prompt, *, count=False):
        self.prompts.append(prompt); self.calls.append('count' if count else 'generate')
        if count: return 200, b'{"totalTokens":100}', 0.001
        value = self.items.pop(0)
        if isinstance(value, Exception): raise value
        if isinstance(value, tuple): return value[0], json.dumps(value[1]).encode(), 0.001
        return 200, envelope(value, self.model), 0.001


def cases():
    return [{'id':f'case-{i}', 'question':'Question', 'initial_evidence':[],
             'actions':[{'id':'a','description':'read'}], 'saved_replay':{'a':{'text':'hidden'}}} for i in range(6)]


def main_values(pilot):
    values=[]
    for i in range(6):
        for arm in pilot.ARMS[i % 3:] + pilot.ARMS[:i % 3]:
            if arm == 'B': values += [decision()]
            elif arm == 'B_self_check': values += [decision(), decision()]
            else: values += [decision(), {'issue':False,'critique':''}]
    return values


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        from unittest.mock import patch
        sleep_patcher=patch.object(runner.time,'sleep',lambda _seconds: None)
        sleep_patcher.start(); self.addCleanup(sleep_patcher.stop)
        self.root=Path(self.temp.name); self.pilot,self.sha=runner.load_frozen()
        self.guard=self.pilot.CostGuard('0.75','3.75')
        self.guard.apply_carry({'attempts':31,'estimated_or_reserved_micro_usd':359587})
    def make_runner(self):
        return self.pilot.Pilot(None,self.root,self.guard,carried_count_attempts=7)
    def events(self):
        return [json.loads(x) for x in (self.root/'events.jsonl').read_text().splitlines()]
    def test_original_episode_ast_is_unchanged(self):
        raw=runner.PILOT.read_text(); source=ast.parse(raw)
        node=next(x for x in source.body if isinstance(x,ast.ClassDef) and x.name=='Pilot')
        episode=next(x for x in node.body if isinstance(x,ast.FunctionDef) and x.name=='episode')
        import inspect
        adapted=ast.parse(inspect.getsource(self.pilot.Pilot.episode).lstrip())
        self.assertEqual(ast.dump(episode,include_attributes=False),ast.dump(adapted.body[0],include_attributes=False))
    def test_18_complete_and_single_model_budget_includes_carry(self):
        values=canary_values()+main_values(self.pilot); provider=FakeProvider(values)
        result=runner.run_series(self.pilot,self.make_runner(),cases(),lambda p,m:provider)
        self.assertEqual(result['status'],'completed');self.assertEqual(result['selected_model'],'gemini-3.8-flash')
        self.assertEqual(len(result['results']),18);self.assertEqual(result['attempts'],65)
        self.assertEqual(result['countTokens_total'],7);self.assertEqual(len(provider.items),0)
        self.assertTrue(all('hidden' not in p for p in provider.prompts))
    def test_http_429_kept_once_and_next_slot_continues(self):
        values=canary_values()+[(429,{'error':{'status':'RESOURCE_EXHAUSTED'}})]
        values+=main_values(self.pilot)[1:]
        provider=FakeProvider(values)
        result=runner.run_series(self.pilot,self.make_runner(),cases(),lambda p,m:provider)
        self.assertEqual(result['status'],'completed');self.assertEqual(len(result['results']),18)
        self.assertEqual(result['results'][0]['status'],'technical_failure')
        terminals=[e for e in self.events() if e['event']=='terminal' and e.get('effect')=='succeeded']
        self.assertEqual(len(terminals),34)
        self.assertEqual([e.get('seconds') for e in self.events() if e.get('event') == 'rate_limit_cooldown'], [5])
        self.assertGreaterEqual(result['estimated_or_reserved_micro_usd'],359587+43008)
    def test_two_429_stop_no_resampling(self):
        items=canary_values()+[(429,{'error':{'status':'RESOURCE_EXHAUSTED'}})]*2
        provider=FakeProvider(items)
        result=runner.run_series(self.pilot,self.make_runner(),cases(),lambda p,m:provider)
        self.assertEqual(result['status'],'stopped_consecutive_failures');self.assertEqual(len(result['results']),2)
        self.assertEqual(len(provider.calls),6)
    def test_unavailable_canary_fallback_before_main(self):
        first=FakeProvider([(404,{'error':{'status':'NOT_FOUND'}})])
        second=FakeProvider(canary_values()+main_values(self.pilot),model='gemini-3.7-flash')
        selected=[]
        def factory(p,m): selected.append(m);return first if m.endswith('3.8-flash') else second
        result=runner.run_series(self.pilot,self.make_runner(),cases(),factory)
        self.assertEqual(selected,['gemini-3.8-flash','gemini-3.7-flash'])
        self.assertEqual(result['status'],'completed');self.assertEqual(result['selected_model'],'gemini-3.7-flash')
        self.assertEqual(result['attempts'],66)
    def test_one_429_canary_does_not_trigger_fallback(self):
        provider=FakeProvider([(429,{'error':{'status':'RESOURCE_EXHAUSTED'}})])
        selected=[]
        result=runner.run_series(self.pilot,self.make_runner(),cases(),lambda p,m:(selected.append(m) or provider))
        self.assertEqual(selected,['gemini-3.8-flash']);self.assertEqual(result['status'],'stopped_canary')
        self.assertEqual(result['attempts'],32)
    def test_uncertain_transport_stops_and_is_not_retried(self):
        provider=FakeProvider([TimeoutError()]);selected=[]
        result=runner.run_series(self.pilot,self.make_runner(),cases(),lambda p,m:(selected.append(m) or provider))
        self.assertEqual(result['status'],'stopped_canary');self.assertEqual(result['attempts'],32)
        self.assertEqual(len(provider.calls),1);self.assertEqual(selected,['gemini-3.8-flash'])
    def test_count_tokens_87_limit(self):
        pilot=self.make_runner();pilot.provider=FakeProvider([]);pilot.slot='test';pilot.token_count_attempts=87
        with self.assertRaises(self.pilot.TechnicalFailure): pilot.call('test','x'*17000,{})
        self.assertEqual(self.guard.attempts,31)
    def test_attempt_111_limit(self):
        self.guard.attempts=111
        with self.assertRaises(self.pilot.StopRun): self.guard.begin()
    def test_incomplete_canary_stops_before_main(self):
        provider=FakeProvider([decision(),{'issue':True,'critique':'test'},decision()])
        result=runner.run_series(self.pilot,self.make_runner(),cases(),lambda p,m:provider)
        self.assertEqual(result['status'],'stopped_canary');self.assertEqual(result['results'],[])
    def test_wrong_model_version_never_reaches_main(self):
        items=canary_values()
        provider=FakeProvider(items,model="gemini-3.7-flash")
        result=runner.run_series(self.pilot,self.make_runner(),cases(),lambda p,m:provider)
        self.assertEqual(result["status"],"stopped_model_version")
        self.assertEqual(result["results"],[])

    def test_global_fence_prevents_second_dispatch_even_in_other_directory(self):
        from unittest.mock import patch
        provider=FakeProvider(canary_values()+main_values(self.pilot))
        def factory(p,m): return provider
        args=["runner.py","--output",str(self.root/"first"),"--execute-live"]
        with patch.object(runner,"LOCK",self.root/"global.lock"), patch.object(runner,"Transport",factory):
            with patch("sys.argv",args): runner.main()
            call_count=len(provider.calls)
            args[2]=str(self.root/"second")
            with patch("sys.argv",args), self.assertRaises(FileExistsError): runner.main()
            self.assertEqual(len(provider.calls),call_count)
            self.assertFalse((self.root/"second").exists())

    def test_missing_usage_stops_with_reservation(self):
        provider=FakeProvider([envelope(decision(),usage={})])
        # FakeProvider needs literal bytes passthrough here.
        provider.request=lambda prompt, count=False:(200,envelope(decision(),usage={}),0.001)
        result=runner.run_series(self.pilot,self.make_runner(),cases(),lambda p,m:provider)
        self.assertEqual(result['status'],'stopped_canary');self.assertEqual(self.guard.used,359587+43008)


if __name__ == '__main__': unittest.main()
