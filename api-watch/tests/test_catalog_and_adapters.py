import json,tempfile
from datetime import timedelta
from pathlib import Path
from django.test import SimpleTestCase
from django.utils import timezone
from watchtower.engine import evaluate
from watchtower.catalog import parse_markdown,sync
from watchtower.registry import TARGETS

class ExpandedAdaptersTests(SimpleTestCase):
 def evaluate(self,spec,body):return evaluate(spec,{'status':200,'duration_ms':150,'body':json.dumps(body)},timezone.now())
 def test_top_level_array_has_count_types_and_duplicate_checks(self):
  spec=next(t for t in TARGETS if t['slug']=='hacker-news')
  good=self.evaluate(spec,[1,2,3]);self.assertEqual(good['record_count'],3);self.assertTrue(all(c['ok']for c in good['checks']))
  bad=self.evaluate(spec,[1,1,True]);self.assertTrue(any(not c['ok']and c['key']=='duplicates'for c in bad['checks']));self.assertTrue(any(not c['ok']and c['key']=='record:$'for c in bad['checks']))
 def test_http_200_deprecation_error_cannot_pass_array_contract(self):
  spec=next(t for t in TARGETS if t['slug']=='rest-countries');result=self.evaluate(spec,{'success':False,'data':None,'errors':[{'message':'deprecated'}]})
  self.assertFalse(next(c for c in result['checks']if c['key']=='json')['ok']);self.assertEqual(result['observed'],{})
 def test_semantic_error_code_is_not_healthy(self):
  spec=next(t for t in TARGETS if t['slug']=='open-trivia');result=self.evaluate(spec,{'response_code':5,'results':[]})
  self.assertFalse(next(c for c in result['checks']if c['key']=='value:response_code')['ok'])
 def test_reference_api_does_not_fabricate_freshness(self):
  spec=next(t for t in TARGETS if t['slug']=='dog-ceo');result=self.evaluate(spec,{'status':'success','message':'https://example.com/image.jpg'})
  self.assertIsNone(result['data_at']);self.assertFalse(any(c['group']=='freshness'for c in result['checks']))
 def test_unix_seconds_and_weekend_aware_exchange_date(self):
  spec=next(t for t in TARGETS if t['slug']=='exchange-rates');now=timezone.now();r=self.evaluate(spec,{'result':'success','time_last_update_unix':(now-timedelta(hours=12)).timestamp(),'rates':{'KRW':1300}})
  self.assertTrue(all(c['ok']for c in r['checks']))
  spec=next(t for t in TARGETS if t['slug']=='frankfurter');r=self.evaluate(spec,{'date':(now-timedelta(days=3)).date().isoformat(),'base':'USD','rates':{'KRW':1300,'EUR':1,'JPY':150}});self.assertTrue(next(c for c in r['checks']if c['key']=='freshness')['ok'])
 def test_large_ignored_dictionary_cannot_hide_later_schema_fields(self):
  spec={'required':{'zfield':'number'},'schema_ignore_prefixes':['$.dynamic']};result=self.evaluate(spec,{'dynamic':{str(i):i for i in range(600)},'zfield':1})
  self.assertIn('$.zfield',result['observed']);self.assertFalse(any(k.startswith('$.dynamic')for k in result['observed']))
 def test_curated_adapters_are_unique_bounded_https_gets(self):
  self.assertEqual(len(TARGETS),22);self.assertEqual(len({t['slug']for t in TARGETS}),22)
  for target in TARGETS:
   self.assertTrue(target['url'].startswith('https://'));self.assertLessEqual(target['timeout_seconds'],12);self.assertLessEqual(target['max_bytes'],3000000)

class CatalogTests(SimpleTestCase):
 def test_source_auth_is_not_confused_with_connectivity(self):
  raw='### 날씨\n| API | 설명 | 인증 |\n|---|---|---|\n| [Open](https://example.com) | 환경 자료 | No |\n| [Private](https://private.example) | 키 필요 | `apiKey` |'
  rows=parse_markdown(raw,'korea');self.assertEqual([x['auth_type']for x in rows],['none','required']);self.assertEqual(rows[0]['category'],'날씨');self.assertNotIn('connected',rows[0])
 def test_resource_without_auth_column_is_unknown(self):
  rows=parse_markdown('### 자료\n| API | 설명 |\n| [자료](https://example.com) | 소개 |','korea');self.assertEqual(rows[0]['auth_type'],'unknown')
 def test_catalog_daily_idempotence_deduplication_and_atomic_failure(self):
  raw='### 개발\n| API | 설명 | 인증 |\n'+'\n'.join(f'| [API{i}](https://example.com/{i}) | test | No |'for i in range(60))
  with tempfile.TemporaryDirectory()as d:
   p=Path(d)/'catalog.json';data=sync(p,fetcher=lambda _:raw);self.assertEqual(data['count'],60);self.assertEqual(len(data['sources']),2)
   original=p.read_text();self.assertEqual(sync(p,fetcher=lambda _:self.fail('duplicate daily fetch'))['count'],60)
   with self.assertRaises(ValueError):sync(p,fetcher=lambda _:'broken',force=True)
   self.assertEqual(p.read_text(),original)
