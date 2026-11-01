"""Frozen-successor replay support; import and APIs have no provider effects.

A stopped, independently reviewed ledger snapshot is required. Never point to
or hash an active ledger. This module derives no new authorization by itself.
"""
from __future__ import annotations
import hashlib,json,re,sqlite3
from pathlib import Path
class Error(ValueError):pass
class UncertainEffect(Error):pass

def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
PATTERN=re.compile(r'^(count|generation):p1:case-02:(no_news:b|news:c|news:b):(0[1-9]|1[0-9]|2[0-3])(?:~retry([1-3]))?$')

class History:
 def __init__(self,path,expected_sha256):
  p=Path(path)
  if not p.is_absolute() or p.is_symlink() or not p.is_file() or p.resolve()!=p.absolute():raise Error('unsafe parent snapshot')
  data=p.read_bytes()
  if sha(data)!=expected_sha256:raise Error('parent snapshot SHA mismatch')
  # Read-only immutable snapshot is safe only after independently verified stop
  # and WAL checkpoint. Caller/witness must establish those conditions.
  db=sqlite3.connect('file:'+str(p)+'?mode=ro&immutable=1',uri=True);db.row_factory=sqlite3.Row
  try:
   run=db.execute('select stopped,exposure_micro,generation_attempts,count_attempts,source_attempts from run').fetchone()
   if run is None or run[0]!=1:raise Error('predecessor is not durably stopped')
   rows=[dict(x) for x in db.execute("select * from effects where kind in ('count','generation') order by rowid")]
   confirms={r[0] for r in db.execute("select reason from run_events where event='confirmed_model_429'")}
  finally:db.close()
  self.path=p;self.digest=expected_sha256;self.run=tuple(run);self.by_logical={};self.extra_used=0
  for x in rows:
   match=PATTERN.fullmatch(x['id'])
   if match is None or x['kind']!=match[1]:raise Error('predecessor model identity outside permitted arms')
   logical=x['id'].split('~retry')[0];attempt=int(match[4] or 0)
   if attempt:self.extra_used+=1
   if x['request'] is None or sha(bytes(x['request']))!=x['request_hash']:raise Error('damaged prior request')
   if x['response'] is not None and sha(bytes(x['response']))!=x['response_hash']:raise Error('damaged prior response')
   if x['state']=='succeeded' and x['http_status']==429:
    if x['id'] not in confirms or x['actual_micro'] is not None or x['response'] is None:raise Error('429 is not explicitly confirmed')
    try:e=json.loads(x['response'])['error']
    except (ValueError,KeyError,TypeError):raise Error('429 body invalid') from None
    if e.get('code')!=429 or e.get('status')!='RESOURCE_EXHAUSTED':raise Error('429 classification unverified')
    kind='confirmed_429'
   elif x['state']=='succeeded' and x['http_status']==200 and type(x['actual_micro']) is int and x['actual_micro']>=0 and x['response'] is not None:kind='success'
   else:kind='unknown'
   self.by_logical.setdefault(logical,[]).append((attempt,kind,x))
  if self.extra_used>20:raise Error('predecessor retry reserve exceeded')
  for logical,entries in self.by_logical.items():
   entries.sort(key=lambda e:e[0]);numbers=[n for n,_,_ in entries]
   if numbers!=list(range(len(numbers))) or len(entries)>4:raise Error('predecessor retry sequence invalid')
   if any(kind!='confirmed_429' for _,kind,_ in entries[:-1]):raise Error('retry followed success or unknown')
   if any(bytes(x['request'])!=bytes(entries[0][2]['request']) for _,_,x in entries):raise Error('retry request bytes differ')
 def inspect(self,logical,request):
  """Classify one exact logical operation: untouched, success, 429, or unknown.

  `attempts` is consumed physical attempts, not a reset retry counter. A
  confirmed_429 may continue only if caller and successor ledger enforce both
  original operation max 3 extra and the shared total max 20 across ledgers.
  """
  if not PATTERN.fullmatch(logical):raise Error('invalid logical ID')
  entries=self.by_logical.get(logical,[]);raw=canonical(request)
  if not entries:return {'classification':'untouched','attempts':0,'request_sha256':sha(raw)}
  if raw!=bytes(entries[0][2]['request']):raise Error('replay request differs from predecessor bytes')
  _,kind,row=entries[-1]
  if kind=='unknown':return {'classification':'unknown','attempts':len(entries),'request_sha256':sha(raw),'id':row['id']}
  return {'classification':kind,'attempts':len(entries),'request_sha256':sha(raw),'id':row['id'],
   'response':bytes(row['response']),'response_sha256':row['response_hash'],'actual_micro':row['actual_micro'],
   'related_id':row['related_id']}
