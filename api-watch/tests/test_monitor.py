import copy,json,tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from django.test import SimpleTestCase,TestCase,Client
from django.utils import timezone
from django.contrib.auth import get_user_model
from watchtower.engine import evaluate
from watchtower.lab import exercise
from watchtower.models import Target,CheckRun,Incident,DailyBrief,Lease
from watchtower.service import record,checkpoint,restore,run_all,Busy,report
from watchtower.ai_brief import make_daily

SPEC={'slug':'fixture','name':'Fixture','url':'https://example.com/data','required':{'updated':'string','items':'array'},'records_path':'items','record_required':{'id':'string','value':'number'},'id_path':'id','min_records':1,'freshness_path':'updated','time_format':'iso','max_age_seconds':3600,'numeric_rules':{'quality':[0,100]},'warning_latency_ms':3000}
def response(now=None,**changes):
 now=now or timezone.now();data={'updated':now.isoformat(),'items':[{'id':'one','value':1}],'quality':10};data.update(changes);return {'status':200,'duration_ms':123,'body':json.dumps(data),'error':''}
class DetectorTests(SimpleTestCase):
 def test_ten_synthetic_scenarios_use_production_engine(self):
  result=exercise();self.assertEqual(result['passed'],10);self.assertEqual(result['source'],'synthetic')
 def test_false_is_not_a_number(self):
  r=evaluate(SPEC,response(items=[{'id':'one','value':False}]),timezone.now());self.assertTrue(any(c['key']=='record:value'and not c['ok']for c in r['checks']))
 def test_invalid_json_constants_are_rejected(self):
  r=response();r['body']='{"updated":NaN}';self.assertFalse(next(c for c in evaluate(SPEC,r,timezone.now())['checks']if c['key']=='json')['ok'])
 def test_new_field_is_not_a_breaking_change(self):
  now=timezone.now();base=evaluate(SPEC,response(now),now)['observed'];r=evaluate(SPEC,response(now,new='value'),now,base);self.assertTrue(next(c for c in r['checks']if c['key']=='schema-drift')['ok']);self.assertTrue(any(d['change']=='added'for d in r['schema_diff']))
 def test_null_only_baseline_does_not_invent_a_type_contract(self):
  now=timezone.now();base=evaluate(SPEC,response(now,optional=None),now)['observed'];r=evaluate(SPEC,response(now,optional=4),now,base);self.assertFalse(any(d['path']=='$.optional'and d['breaking']for d in r['schema_diff']))
 def test_empty_list_may_be_valid_when_configured(self):
  spec=dict(SPEC,min_records=0);r=evaluate(spec,response(items=[]),timezone.now());self.assertTrue(next(c for c in r['checks']if c['key']=='count')['ok'])
 def test_exact_age_threshold_and_future_skew(self):
  now=timezone.now();r=evaluate(SPEC,response(now-timedelta(seconds=3600)),now);self.assertTrue(next(c for c in r['checks']if c['key']=='freshness')['ok']);r=evaluate(SPEC,response(now+timedelta(minutes=10)),now);self.assertFalse(next(c for c in r['checks']if c['key']=='future-time')['ok'])
 def test_configured_dynamic_dictionary_is_not_a_schema_contract(self):
  now=timezone.now();spec=dict(SPEC,schema_ignore_prefixes=['$.dynamic']);base=evaluate(spec,response(now,dynamic={'one':1}),now)['observed'];r=evaluate(spec,response(now,dynamic={'two':2}),now,base);self.assertFalse(any(d['breaking']for d in r['schema_diff']))
class PersistenceTests(TestCase):
 def setUp(self):self.target=Target.objects.create(slug='fixture',name='Fixture',spec=SPEC);self.now=timezone.now()
 def record(self,r):self.target.refresh_from_db();return record(self.target,r,self.now)
 def test_transient_failure_escalates_and_recovery_closes_one_incident(self):
  bad={'status':503,'error':'HTTP 503','duration_ms':1,'body':''};self.assertEqual(self.record(bad).status,'warning');self.assertEqual(self.record(bad).status,'critical');self.assertEqual(Incident.objects.count(),1);self.assertEqual(Incident.objects.get().occurrences,2);self.assertEqual(self.record(response()).status,'healthy');self.assertIsNotNone(Incident.objects.get().resolved_at)
 def test_unobserved_quality_does_not_recover_during_network_failure(self):
  self.record(response(self.now-timedelta(days=2)));stale=Incident.objects.get(key='freshness');self.record({'status':500,'error':'HTTP 500','duration_ms':1,'body':''});stale.refresh_from_db();self.assertIsNone(stale.resolved_at);self.record(response());stale.refresh_from_db();self.assertIsNotNone(stale.resolved_at)
 def test_bad_response_never_replaces_approved_schema(self):
  self.record(response());self.target.refresh_from_db();before=self.target.baseline;self.record(response(items='bad'));self.target.refresh_from_db();self.assertEqual(self.target.baseline,before)
 def test_checkpoint_restores_history_and_is_idempotent(self):
  self.record(response());
  with tempfile.TemporaryDirectory()as d:
   p=Path(d)/'state.json';checkpoint(p);CheckRun.objects.all().delete();Incident.objects.all().delete();
   with patch('watchtower.service.configure',return_value=None):self.assertTrue(restore(p));self.assertFalse(restore(p))
   self.assertEqual(CheckRun.objects.count(),1)
 def test_busy_lease_prevents_overlapping_requests(self):
  Lease.objects.create(name='monitor',until=timezone.now()+timedelta(minutes=1));
  with self.assertRaises(Busy):run_all(lambda s:response())
 def test_post_requires_staff_and_csrf(self):
  self.assertEqual(self.client.get('/api/run').status_code,405);self.assertEqual(self.client.post('/api/run').status_code,403)
  user=get_user_model().objects.create_user('staff',password='test-only-value',is_staff=True);strict=Client(enforce_csrf_checks=True);strict.force_login(user);self.assertEqual(strict.post('/api/run').status_code,403)
 def test_staff_manual_run_returns_real_report_shape(self):
  user=get_user_model().objects.create_user('staff',password='test-only-value',is_staff=True);self.client.force_login(user)
  with patch('watchtower.views.service.run_all',return_value=[]):r=self.client.post('/api/run')
  self.assertEqual(r.status_code,200);self.assertEqual(r.json()['schema_version'],1)
 def test_source_and_synthetic_labels_stay_separate(self):
  self.record(response());self.assertEqual(report()['history'][0]['source'],'live');self.assertEqual(exercise()['source'],'synthetic')
class DailyBriefTests(TestCase):
 def fake_release(self,url):
  if 'huggingface.co' in url:return []
  repo=url.split('/repos/')[1].split('/releases')[0];return[{'id':repo,'published_at':(timezone.now()-timedelta(minutes=1)).isoformat(),'draft':False,'prerelease':False,'name':'Stable test','tag_name':'v1-test','body':'A documented compatibility change.','html_url':'https://github.com/'+repo+'/releases/tag/v1-test'}]
 def test_exactly_one_item_per_korean_day(self):
  row,created=make_daily(self.fake_release);self.assertTrue(created);self.assertEqual(row.payload['kind'],'release')
  with patch('watchtower.ai_brief.get_json',side_effect=AssertionError('must not fetch')):again,created=make_daily(lambda _:(_ for _ in ()).throw(AssertionError()))
  self.assertFalse(created);self.assertEqual(row.pk,again.pk);self.assertEqual(DailyBrief.objects.count(),1)
 def test_failure_is_labelled_as_existing_learning_not_new_release(self):
  row,_=make_daily(lambda _:(_ for _ in ()).throw(OSError('offline')));self.assertEqual(row.payload['kind'],'reading');self.assertIsNone(row.payload['official_published_at']);self.assertTrue(row.payload['fetch_errors'])
 def test_model_update_is_not_claimed_to_be_a_release_date(self):
  def source(url):
   if 'huggingface.co' in url:return[{'id':'Qwen/Test-Model','lastModified':(timezone.now()-timedelta(minutes=1)).isoformat(),'pipeline_tag':'text-generation','cardData':{'license':'apache-2.0'}}]
   return []
  row,_=make_daily(source);self.assertEqual(row.payload['kind'],'model');self.assertIsNone(row.payload['official_published_at']);self.assertIn('최초 발표일과 구분',row.payload['label'])
 def test_untrusted_release_url_is_not_published(self):
  row,_=make_daily(lambda u:[]if'huggingface.co'in u else[{'id':1,'published_at':(timezone.now()-timedelta(minutes=1)).isoformat(),'html_url':'javascript:bad()','draft':False,'prerelease':False}]);self.assertEqual(row.payload['kind'],'reading')
