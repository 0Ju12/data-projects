import json,time,uuid,urllib.request,urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta,timezone as dt_timezone,datetime
from pathlib import Path
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import Target,CheckRun,Incident,Lease,DailyBrief
from .registry import TARGETS
from .engine import evaluate
class Busy(Exception):pass

def fetch(spec):
 start=time.monotonic();result={'status':None,'duration_ms':0,'body':'','error':''}
 try:
  request=urllib.request.Request(spec['url'],headers={'User-Agent':'0Ju12-API-Watch/1.0 (+https://github.com/0Ju12/data-projects)'})
  with urllib.request.urlopen(request,timeout=spec.get('timeout_seconds',12))as response:
   result['status']=response.status;raw=response.read(spec.get('max_bytes',3000000)+1)
   if len(raw)>spec.get('max_bytes',3000000):result['error']='응답 크기 제한 초과'
   else:result['body']=raw.decode('utf-8')
 except urllib.error.HTTPError as e:result['status']=e.code;result['error']='HTTP '+str(e.code)
 except (urllib.error.URLError,TimeoutError,OSError,UnicodeError)as e:result['error']=type(e).__name__+' · 응답을 읽지 못했습니다.'
 result['duration_ms']=round((time.monotonic()-start)*1000,2);return result

def configure():
 for spec in TARGETS:
  target,_=Target.objects.get_or_create(slug=spec['slug'],defaults={'name':spec['name'],'spec':spec})
  if target.spec!=spec or target.name!=spec['name']:target.spec=spec;target.name=spec['name'];target.save(update_fields=['spec','name'])

def record(target,response,now):
 result=evaluate(target.spec,response,now,target.baseline);failed=[c for c in result['checks']if not c['ok']];hard=[c for c in failed if c['severity']=='error']
 availability_failed=any(c['key']=='availability'for c in hard)
 target.consecutive_failures=target.consecutive_failures+1 if availability_failed else 0
 status='critical'if hard else'warning'if failed else'healthy'
 if availability_failed and target.consecutive_failures==1:status='warning'
 if status=='healthy':
  target.last_success=now
  if not target.baseline:target.baseline=result['observed']
 target.save()
 run=CheckRun.objects.create(target=target,checked_at=now,status=status,http_status=response.get('status'),duration_ms=response.get('duration_ms',0),data_at=result['data_at'],record_count=result['record_count'],checks=result['checks'],schema_diff=result['schema_diff'],error=response.get('error','')[:300])
 evaluated={c['key']for c in result['checks']};failed_keys={c['key']for c in failed}
 for issue in failed:
  severity='warning'if issue['key']=='availability'and target.consecutive_failures<2 else issue['severity']
  incident=Incident.objects.filter(target=target,key=issue['key'],resolved_at__isnull=True).first()
  if incident:incident.last_seen_at=now;incident.occurrences+=1;incident.message=issue['detail'];incident.severity=severity;incident.save()
  else:Incident.objects.create(target=target,key=issue['key'],kind=issue['group'],severity=severity,message=issue['detail'],opened_at=now,last_seen_at=now)
 # Unobserved checks stay open: a network failure cannot prove data quality recovered.
 Incident.objects.filter(target=target,resolved_at__isnull=True,key__in=evaluated-failed_keys).update(resolved_at=now)
 return run

def run_all(fetcher=fetch):
 configure();now=timezone.now();token=uuid.uuid4().hex;Lease.objects.get_or_create(name='monitor')
 locked=Lease.objects.filter(name='monitor').filter(Q(until__isnull=True)|Q(until__lte=now)).update(token=token,until=now+timedelta(minutes=3))
 if not locked:raise Busy('다른 검사가 실행 중입니다.')
 try:
  targets=list(Target.objects.order_by('slug'));runs=[]
  with ThreadPoolExecutor(max_workers=6)as pool:responses=list(pool.map(fetcher,[t.spec for t in targets]))
  for target,response in zip(targets,responses):
   with transaction.atomic():runs.append(record(target,response,timezone.now()))
  return runs
 finally:Lease.objects.filter(name='monitor',token=token).update(until=None,token='')

def run_dict(r):return {'id':r.id,'target':r.target_id,'checked_at':r.checked_at.isoformat(),'status':r.status,'http_status':r.http_status,'duration_ms':r.duration_ms,'data_at':r.data_at.isoformat()if r.data_at else None,'record_count':r.record_count,'checks':r.checks,'schema_diff':r.schema_diff,'error':r.error,'source':r.source}
def incident_dict(i):return {'id':i.id,'target':i.target_id,'key':i.key,'kind':i.kind,'severity':i.severity,'message':i.message,'opened_at':i.opened_at.isoformat(),'last_seen_at':i.last_seen_at.isoformat(),'resolved_at':i.resolved_at.isoformat()if i.resolved_at else None,'occurrences':i.occurrences}
def report():
 targets=[];history=[]
 for target in Target.objects.order_by('slug'):
  runs=list(target.runs.all()[:72]);history.extend(run_dict(r)for r in runs)
  targets.append({'slug':target.slug,'name':target.name,'spec':target.spec,'last_run':run_dict(runs[0])if runs else None,'last_success':target.last_success.isoformat()if target.last_success else None,'consecutive_failures':target.consecutive_failures,'baseline_fields':len(target.baseline)})
 briefs=list(DailyBrief.objects.all()[:90]);latest=max((r['checked_at']for r in history),default=None)
 return {'schema_version':1,'generated_at':timezone.now().isoformat(),'last_check_at':latest,'expected_interval_seconds':3600,'targets':targets,'history':sorted(history,key=lambda r:r['checked_at'],reverse=True),'incidents':[incident_dict(i)for i in Incident.objects.all()[:200]],'ai_latest':briefs[0].payload if briefs else None,'ai_archive':[b.payload for b in briefs],'mode':'scheduled-report','provenance':'실제 HTTP 요청의 검사 결과입니다. 합성 장애 실험은 lab.json으로 분리합니다.'}

def workspace_feed(data):
 # Only public, current signals cross into the private learning app; history stays here.
 targets=[]
 for t in data['targets']:
  latest=t.get('last_run')
  targets.append({'slug':t['slug'],'name':t['name'],'spec':{k:t['spec'].get(k)for k in ['category','description','docs']},'last_run':{k:latest.get(k)for k in ['status','checked_at','duration_ms']}if latest else None})
 return {'schema_version':1,'last_check_at':data['last_check_at'],'targets':targets,'incidents':[i for i in data['incidents']if not i['resolved_at']],'ai_latest':data['ai_latest'],'ai_archive':data['ai_archive']}

def export_files(directory):
 directory=Path(directory);directory.mkdir(parents=True,exist_ok=True);data=report()
 for name,value in [('report.json',data),('workspace.json',workspace_feed(data)),('lab.json',__import__('watchtower.lab',fromlist=['exercise']).exercise())]:
  path=directory/name;tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2));tmp.replace(path)
 return data

def checkpoint(path):
 data=report();data['target_state']=[{'slug':t.slug,'baseline':t.baseline,'consecutive_failures':t.consecutive_failures,'last_success':t.last_success.isoformat()if t.last_success else None}for t in Target.objects.all()]
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(path)

def restore(path):
 if CheckRun.objects.exists():return False
 path=Path(path)
 if not path.exists():return False
 data=json.loads(path.read_text())
 if data.get('schema_version')!=1:raise ValueError('체크포인트 형식 오류')
 configure();known=set(Target.objects.values_list('slug',flat=True))
 with transaction.atomic():
  for row in data.get('target_state',[]):
   if row['slug']in known:Target.objects.filter(slug=row['slug']).update(baseline=row['baseline'],consecutive_failures=row['consecutive_failures'],last_success=row.get('last_success'))
  for row in data.get('history',[]):
   row=dict(row);slug=row.pop('target');row.pop('id',None)
   if slug in known:CheckRun.objects.create(target_id=slug,**row)
  for row in data.get('incidents',[]):
   row=dict(row);slug=row.pop('target');row.pop('id',None)
   if slug in known:Incident.objects.create(target_id=slug,**row)
  for row in data.get('ai_archive',[]):DailyBrief.objects.get_or_create(date=row['date'],defaults={'item_id':row['item_id'],'created_at':row['created_at'],'payload':row})
 return True
