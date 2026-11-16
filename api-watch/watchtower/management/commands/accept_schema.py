from django.core.management.base import BaseCommand,CommandError
from django.utils import timezone
from watchtower.models import Target
from watchtower.service import fetch
from watchtower.engine import evaluate
class Command(BaseCommand):
 help='원문·변경을 검토한 뒤 승인할 응답 구조를 갱신합니다.'
 def add_arguments(self,p):p.add_argument('slug');p.add_argument('--confirm',action='store_true')
 def handle(self,*args,**o):
  if not o['confirm']:raise CommandError('검토 후 --confirm을 명시하세요.')
  try:t=Target.objects.get(slug=o['slug'])
  except Target.DoesNotExist:raise CommandError('없는 검사 대상입니다.')
  r=evaluate(t.spec,fetch(t.spec),timezone.now())
  if any(not c['ok']and c['severity']=='error'for c in r['checks']):raise CommandError('필수·품질 검사를 통과하지 못해 승인하지 않았습니다.')
  t.baseline=r['observed'];t.save(update_fields=['baseline']);self.stdout.write('구조 승인: '+t.slug)
