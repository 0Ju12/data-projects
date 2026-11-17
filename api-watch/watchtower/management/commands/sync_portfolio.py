from django.core.management.base import BaseCommand,CommandError
from watchtower.portfolio_sync import sync
class Command(BaseCommand):
 help='최신 GitHub 공개 프로젝트·AI 글·통합 준비 공간 연결을 버전 고정으로 동기화'
 def add_arguments(self,p):p.add_argument('--output',default='public/portfolio.json');p.add_argument('--force',action='store_true')
 def handle(self,*args,**options):
  try:data=sync(options['output'],force=options['force'])
  except Exception as e:raise CommandError('공개 포트폴리오 동기화 실패 · 기존 파일 유지: '+type(e).__name__)
  self.stdout.write(f"공개 프로젝트 {len(data['projects'])}개 · AI 글 {len(data['learning_notes'])}개 · {data['source_sha'][:8]}")
