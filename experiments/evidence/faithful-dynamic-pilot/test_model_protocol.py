import json
import unittest
from model_protocol import request, parse

class ProtocolTests(unittest.TestCase):
    def test_inference_and_formatter_receive_only_projected_input(self):
        for stage, payload in [('inference', {'selected_texts':['premise']}),
                               ('formatter', {'current_inference':'result','contract_ids':['m'], 'allowed_labels':['unknown']})]:
            body=request(stage,payload)
            item=json.loads(body['contents'][0]['parts'][0]['text'])
            self.assertEqual(item['input'], payload)
            self.assertNotIn('QUESTION_SENTINEL', json.dumps(body))
            self.assertEqual(body['generationConfig']['maxOutputTokens'],4096)
    def test_parse_requires_complete_single_json_candidate(self):
        response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"score":0.5}'}]}}]}
        self.assertEqual(parse(response),{'score':0.5})
        response['candidates'][0]['finishReason']='MAX_TOKENS'
        with self.assertRaises(ValueError): parse(response)
        response['candidates'][0]['finishReason']='STOP'
        response['candidates'][0]['content']['parts'][0]['text']='not json'
        with self.assertRaises(ValueError): parse(response)
    def test_unknown_stage_rejected(self):
        with self.assertRaises(ValueError): request('other',{})

if __name__=='__main__': unittest.main()
