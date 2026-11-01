import importlib.util
from pathlib import Path
import json
import pytest
p=Path(__file__).with_name('news_projection.py')
s=importlib.util.spec_from_file_location('news_projection',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)

def encoded(items): return json.dumps({'success':True,'data':{'news':items}}).encode()

def test_raw_preserved_and_first_three_in_provider_order():
    raw=encoded([{'title':str(i)} for i in range(10)])
    x=m.project(raw)
    assert x['provider_returned_count']==10 and x['selected_count']==3
    assert x['provider_honored_num'] is False
    assert x['fields']==[('news:0:title','0'),('news:1:title','1'),('news:2:title','2')]
    assert raw==encoded([{'title':str(i)} for i in range(10)])

def test_empty_is_valid_and_missing_is_not():
    assert m.project(encoded([]))['fields']==[]
    with pytest.raises(m.ProjectionError): m.project(b'{"success":true,"data":{}}')

def test_rejects_unbounded_nonobjects_and_bad_selected_fields():
    for news in ([{}]*101,[{},None], [{'title':123}]):
        with pytest.raises(m.ProjectionError): m.project(encoded(news))

def test_reject_duplicate_json_key():
    with pytest.raises(m.ProjectionError): m.project(b'{"success":true,"success":false,"data":{"news":[]}}')
