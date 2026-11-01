"""Preserve the exact source response; select a fixed, ordered first three.

Provider may return more than requested despite num=3. This deterministic,
content-independent projection is a post-capture protocol amendment and is not
a claim that the provider honored num. No source or model effects happen here.
"""
import hashlib
import json

class ProjectionError(ValueError): pass

def pairs(items):
    out={}
    for key,value in items:
        if key in out: raise ProjectionError('duplicate JSON key')
        out[key]=value
    return out

def project(raw):
    if not isinstance(raw,bytes) or len(raw)>524288: raise ProjectionError('invalid response size')
    try: data=json.loads(raw,object_pairs_hook=pairs)
    except (ValueError,UnicodeDecodeError) as exc: raise ProjectionError('malformed response JSON') from exc
    if not isinstance(data,dict) or data.get('success') is not True or not isinstance(data.get('data'),dict):
        raise ProjectionError('invalid response envelope')
    news=data['data'].get('news')
    if not isinstance(news,list) or len(news)>100 or any(not isinstance(item,dict) for item in news):
        raise ProjectionError('news missing or exceeds safety bound')
    fields=[]
    for i,item in enumerate(news[:3]):
        for key in ('title','link','source','date','snippet'):
            value=item.get(key)
            if value is None or value=='': continue
            if not isinstance(value,str): raise ProjectionError('selected news field must be text')
            fields.append((f'news:{i}:{key}',value))
    return {'raw_sha256':hashlib.sha256(raw).hexdigest(),'provider_returned_count':len(news),
            'selected_count':min(3,len(news)),'selection':'provider order, first up to 3; content-independent',
            'request_num':3,'provider_honored_num':len(news)<=3,'fields':fields}
