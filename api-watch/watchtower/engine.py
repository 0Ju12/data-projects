"""Pure detector. Network, storage, and synthetic exercises are kept outside this module."""
import json,math
from datetime import datetime,timezone
MISSING=object()
def at(data,path):
 if path=='$':return data
 for part in path.split('.') if path else []:
  if not isinstance(data,dict)or part not in data:return MISSING
  data=data[part]
 return data
def kind(x):
 if x is MISSING:return 'missing'
 if x is None:return 'null'
 if isinstance(x,bool):return 'boolean'
 if isinstance(x,(int,float)):return 'number'
 if isinstance(x,str):return 'string'
 if isinstance(x,list):return 'array'
 return 'object'
def signature(value,path='$',out=None,depth=0,ignore=()):
 out={}if out is None else out
 if depth>8 or len(out)>=512 or any(path==prefix or path.startswith(prefix+'.')for prefix in ignore):return out
 out.setdefault(path,set()).add(kind(value))
 if isinstance(value,dict):
  for k,v in sorted(value.items()):signature(v,path+'.'+k,out,depth+1,ignore)
 elif isinstance(value,list):
  for v in value[:25]:signature(v,path+'[]',out,depth+1,ignore)
 return out
def parse_time(value,fmt):
 if fmt=='unix':return datetime.fromtimestamp(float(value),timezone.utc)
 if fmt=='unix_ms':return datetime.fromtimestamp(float(value)/1000,timezone.utc)
 if fmt=='utc_minute':return datetime.strptime(value,'%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
 parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
 return parsed.replace(tzinfo=timezone.utc)if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
def evaluate(spec,response,now,baseline=None):
 checks=[];diff=[];data_at=None;count=None;observed={}
 def check(key,label,ok,detail,group,severity='error'):checks.append({'key':key,'label':label,'ok':bool(ok),'detail':detail[:450],'group':group,'severity':severity})
 code=response.get('status');error=response.get('error','');elapsed=response.get('duration_ms',0)
 check('availability','HTTP 응답',bool(code and 200<=code<300 and not error),error or 'HTTP '+str(code),'availability')
 if not checks[-1]['ok']:return {'checks':checks,'schema_diff':diff,'data_at':None,'record_count':None,'observed':observed}
 check('latency','응답 시간',elapsed<=spec.get('warning_latency_ms',3000),f'{elapsed:.0f} ms · 기준 {spec.get("warning_latency_ms",3000)} ms','latency','warning')
 try:
  data=json.loads(response['body'],parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)));valid=kind(data)==spec.get('json_root','object')
 except (ValueError,TypeError,KeyError):data=None;valid=False
 check('json','JSON 해석',valid,'JSON '+spec.get('json_root','object')+' 응답'if valid else'기대 JSON '+spec.get('json_root','object')+' 형식과 다르거나 해석할 수 없습니다.','format')
 if not valid:return {'checks':checks,'schema_diff':diff,'data_at':None,'record_count':None,'observed':observed}
 for path,expected in spec.get('required',{}).items():
  actual=kind(at(data,path));check('field:'+path,'필수 필드 · '+path,actual==expected,f'기대 {expected} · 실제 {actual}','schema')
 for path,expected in spec.get('expected_values',{}).items():
  actual=at(data,path);check('value:'+path,'응답 의미 · '+path,kind(actual)==kind(expected)and actual==expected,f'기대 {expected} · 실제 {actual if actual is not MISSING else "없음"}','quality')
 observed={k:sorted(v)for k,v in signature(data,ignore=spec.get('schema_ignore_prefixes',[])).items()if not any(k==prefix or k.startswith(prefix+'.')for prefix in spec.get('schema_ignore_prefixes',[]))}
 for path,types in (baseline or {}).items():
  if any(path==prefix or path.startswith(prefix+'.')for prefix in spec.get('schema_ignore_prefixes',[])):continue
  if path not in observed:
   # Array child paths are unobservable when the list is empty, not necessarily removed.
   if '[]'not in path:diff.append({'path':path,'change':'removed','before':types,'after':[],'breaking':True})
  elif (set(types)-{'null'})and(set(observed[path])-set(types)-{'null'}):diff.append({'path':path,'change':'type_changed','before':types,'after':observed[path],'breaking':True})
 for path,types in observed.items():
  if baseline and path not in baseline:diff.append({'path':path,'change':'added','before':[],'after':types,'breaking':False})
 if baseline:check('schema-drift','이전 승인 구조와 비교',not any(d['breaking']for d in diff),f'변경 {len(diff)}개 · 추가 필드는 정보로만 표시','schema')
 path=spec.get('records_path')
 if path:
  records=at(data,path)
  if isinstance(records,list):
   count=len(records);minimum=spec.get('min_records');check('count','결과 건수',minimum is None or count>=minimum,f'{count}건 · 최소 {minimum if minimum is not None else "제한 없음"}','quality')
   for field,expected in spec.get('record_required',{}).items():
    bad=sum(kind(at(row,field))!=expected for row in records);check('record:'+field,'항목 필드 · '+field,bad==0,f'{len(records)}건 중 누락·자료형 오류 {bad}건','schema')
   field=spec.get('id_path')
   if field:
    ids=[at(row,field)for row in records];missing=sum(x is MISSING or x is None for x in ids);texts=[json.dumps(x,sort_keys=True)for x in ids if x is not MISSING and x is not None];duplicates=len(texts)-len(set(texts));check('duplicates','식별자 중복',duplicates==0 and missing==0,f'중복 {duplicates}건 · 식별자 없음 {missing}건','quality')
 for path,bounds in spec.get('numeric_rules',{}).items():
  v=at(data,path);valid=kind(v)=='number'and math.isfinite(v)and bounds[0]<=v<=bounds[1];check('range:'+path,'값 범위 · '+path,valid,f'허용 {bounds[0]}~{bounds[1]} · 실제 {str(v)if v is not MISSING else "없음"}','quality')
 if not spec.get('freshness_path'):return {'checks':checks,'schema_diff':diff,'data_at':None,'record_count':count,'observed':observed}
 try:
  data_at=parse_time(at(data,spec['freshness_path']),spec['time_format']);age=(now-data_at).total_seconds();check('future-time','미래 시각 검사',age>=-300,f'현재 대비 {age:.0f}초 전','freshness');check('freshness','데이터 최신성',age<=spec['max_age_seconds'],f'{max(0,age)/60:.1f}분 경과 · 허용 {spec["max_age_seconds"]/60:g}분','freshness')
 except (ValueError,TypeError,OverflowError,OSError,AttributeError):check('time-format','기준 시각 해석',False,'기준 시각이 없거나 형식이 올바르지 않습니다.','freshness')
 return {'checks':checks,'schema_diff':diff,'data_at':data_at,'record_count':count,'observed':observed}
