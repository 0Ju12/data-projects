from django.core.management.base import BaseCommand,CommandError
from watchtower.catalog import sync
class Command(BaseCommand):
 help='한국·글로벌 API/리소스 목록을 하루 한 번 동기화 (엔드포인트 실행과 별개)'
 def add_arguments(self,p):p.add_argument('--output',default='public/catalog.json');p.add_argument('--force',action='store_true')
 def handle(self,*args,**options):
  try:data=sync(options['output'],force=options['force'])
  except Exception as e:raise CommandError('목록 동기화 실패: '+type(e).__name__)
  self.stdout.write(f"API·리소스 목록 {data['count']}개 · {data['sync_date']}")
