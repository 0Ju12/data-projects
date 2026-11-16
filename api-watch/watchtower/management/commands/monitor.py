from django.core.management.base import BaseCommand,CommandError
from watchtower.service import run_all,restore,checkpoint,export_files,Busy
from watchtower.ai_brief import make_daily
class Command(BaseCommand):
 help='실제 API 검사, 하루 1개 AI 기술 노트, 정적 보고서·체크포인트 생성'
 def add_arguments(self,p):
  p.add_argument('--output',default='public');p.add_argument('--checkpoint',default='state/checkpoint.json');p.add_argument('--skip-ai',action='store_true')
 def handle(self,*args,**options):
  restore(options['checkpoint'])
  try:runs=run_all()
  except Busy as e:raise CommandError(str(e))
  if not options['skip_ai']:
   note,created=make_daily();self.stdout.write('AI 학습 노트: '+note.payload['title']+(' (새 글)'if created else' (오늘 기록 유지)'))
  export_files(options['output']);checkpoint(options['checkpoint'])
  self.stdout.write('실제 검사: '+', '.join(r.target_id+'='+r.status for r in runs))
