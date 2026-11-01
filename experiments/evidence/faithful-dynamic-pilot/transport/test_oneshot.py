import unittest
from unittest import mock
import httpx
from oneshot import OneShotTransport, TransportError

class Tests(unittest.TestCase):
 def test_exact_allowed_urls_body_and_auth(self):
  seen=[]; tokens=[]
  def handler(r):
   seen.append((str(r.url),r.method,r.read(),r.headers['authorization'],r.headers['accept-encoding']))
   return httpx.Response(200,stream=httpx.ByteStream(b'{"ok":true}'))
  t=OneShotTransport('project-123',lambda p: tokens.append(p) or 'test-token',http_transport=httpx.MockTransport(handler))
  for provider, endpoint in [('vertex','countTokens'),('vertex','gemini-3.8-flash@global'),('orthogonal','/v1/run')]:
   self.assertEqual(t(provider,endpoint,b'{"hello":1}'),(200,b'{"ok":true}'))
  self.assertEqual(tokens,['vertex','vertex','orthogonal'])
  self.assertEqual(seen[0][0],'https://aiplatform.googleapis.com/v1/projects/project-123/locations/global/publishers/google/models/gemini-3.8-flash:countTokens')
  self.assertTrue(seen[1][0].endswith('gemini-3.8-flash:generateContent'))
  self.assertEqual(seen[2][0],'https://api.orthogonal.com/v1/run')
  self.assertTrue(all(x[1:] == ('POST',b'{"hello":1}','Bearer test-token','identity') for x in seen))
 def test_unknown_endpoint_rejected_before_auth_or_network(self):
  seen=[]; t=OneShotTransport('project-123',lambda p:seen.append('token') or 'secret',http_transport=httpx.MockTransport(lambda r:seen.append('request')))
  for p,e in [('vertex','gemini-3.7-flash@global'),('vertex','metadata'),('orthogonal','/v1/search'),('other','/v1/run')]:
   with self.assertRaises(ValueError): t(p,e,b'{}')
  self.assertEqual(seen,[])
 def test_redirect_response_returned_without_following(self):
  seen=[]
  def handler(r): seen.append(str(r.url)); return httpx.Response(302,headers={'location':'https://example.com'},stream=httpx.ByteStream(b'redirect'))
  t=OneShotTransport('project-123',lambda p:'token',http_transport=httpx.MockTransport(handler))
  self.assertEqual(t('orthogonal','/v1/run',b'{}'),(302,b'redirect'))
  self.assertEqual(len(seen),1)
 def test_http_failure_not_retried_and_error_sanitized(self):
  seen=[]
  def handler(r): seen.append(1); raise httpx.ReadTimeout('secret-value')
  t=OneShotTransport('project-123',lambda p:'secret-value',http_transport=httpx.MockTransport(handler))
  with self.assertRaises(TransportError) as e: t('orthogonal','/v1/run',b'{}')
  self.assertEqual(len(seen),1); self.assertNotIn('secret-value',str(e.exception)); self.assertTrue(e.exception.__suppress_context__)
 def test_credential_error_sanitized_and_blocks_network(self):
  seen=[]
  def token(p): raise RuntimeError('secret-value')
  t=OneShotTransport('project-123',token,http_transport=httpx.MockTransport(lambda r:seen.append(1)))
  with self.assertRaises(TransportError) as e: t('vertex','countTokens',b'{}')
  self.assertNotIn('secret-value',str(e.exception)); self.assertEqual(seen,[])
 def test_invalid_credentials_and_request_block_network(self):
  seen=[]
  for token in ('', 'bad\r\nheader',' space','токен'):
   t=OneShotTransport('project-123',lambda p:token,http_transport=httpx.MockTransport(lambda r:seen.append(1)))
   with self.assertRaises(TransportError): t('vertex','countTokens',b'{}')
  t=OneShotTransport('project-123',lambda p:'ok',http_transport=httpx.MockTransport(lambda r:seen.append(1)))
  for body in (b'',b'a'*2_000_001,'not-bytes'):
   with self.assertRaises(ValueError): t('vertex','countTokens',body)
  self.assertEqual(seen,[])
 def test_oversize_response_never_returns_partial_content(self):
  seen=[]
  def handler(r): seen.append(1); return httpx.Response(200,stream=httpx.ByteStream(b'x'*524289))
  t=OneShotTransport('project-123',lambda p:'token',http_transport=httpx.MockTransport(handler))
  with self.assertRaisesRegex(TransportError,'capture limit'): t('orthogonal','/v1/run',b'{}')
  self.assertEqual(seen,[1])
 def test_default_config_has_no_http_retry_or_redirect(self):
  engine=httpx.MockTransport(lambda r:httpx.Response(200,stream=httpx.ByteStream(b'{}')))
  with mock.patch('oneshot.httpx.HTTPTransport',return_value=engine) as factory, mock.patch('oneshot.httpx.Client', wraps=httpx.Client) as client:
   t=OneShotTransport('project-123',lambda p:'token')
   self.assertEqual(t('vertex','countTokens',b'{}'),(200,b'{}'))
   factory.assert_called_once_with(retries=0)
   self.assertFalse(client.call_args.kwargs['follow_redirects']); self.assertFalse(client.call_args.kwargs['trust_env'])
   self.assertEqual(client.call_args.kwargs['timeout'].read,420.0)
 def test_invalid_project_blocks_transport(self):
  for project in ('../evil','http://x','bad project','UPPERCASE','short'):
   with self.assertRaises(ValueError): OneShotTransport(project,lambda p:'token')

class LedgerTransportIntegration(unittest.TestCase):
 def test_single_journal_all_three_effects_and_no_secret_persistence(self):
  import sys, tempfile
  from pathlib import Path
  budget = str(Path(__file__).resolve().parent.parent / 'budget-v2')
  sys.path.insert(0,budget)
  try:
   from ledger import Ledger, digest, canonical
   from test_ledger import contract, request
   calls=[]
   def handler(r):
    calls.append((str(r.url),r.read()))
    if str(r.url).endswith(':countTokens'): data=b'{"totalTokens":100}'
    elif str(r.url).endswith(':generateContent'): data=b'{"modelVersion":"gemini-3.8-flash","usageMetadata":{"promptTokenCount":100,"totalTokenCount":150,"thoughtsTokenCount":40}}'
    else: data=b'{"priceCents":0.25,"data":{"results":[]}}'
    return httpx.Response(200,stream=httpx.ByteStream(data))
   with tempfile.TemporaryDirectory() as d:
    l=Ledger(str(Path(d).resolve() / 'run'),contract(),create=True)
    t=OneShotTransport('project-123',lambda p:'integration-secret',http_transport=httpx.MockTransport(handler))
    l.count('count',request(),t); l.generate('generation',request(),'count',t)
    body=canonical({'api':'serper','path':'/news','body':{'q':'fixture','num':3},'query':{}})
    q={'provider':'orthogonal','endpoint':'/v1/run','request_sha256':digest(body),'max_micro':2500,'evidence_sha256':'a'*64,'expires_utc':'2099-01-01T00:00:00Z'}
    l.source('source','orthogonal','/v1/run',body,q,t)
    self.assertEqual(len(calls),3)
    self.assertEqual(calls[0][1],calls[1][1])
    self.assertEqual(l.summary()['exposure_micro'],721593+525+2500)
    self.assertEqual(l.receipt('source')['actual_micro'],2500)
    l.close()
    self.assertNotIn(b'integration-secret',(Path(d)/'run'/'ledger.sqlite3').read_bytes())
  finally:
   sys.path.remove(budget)

if __name__=='__main__': unittest.main()
