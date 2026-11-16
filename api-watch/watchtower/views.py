from pathlib import Path
from django.conf import settings
from django.http import JsonResponse,HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from . import service
from .lab import exercise
@ensure_csrf_cookie
def dashboard(request):return HttpResponse((Path(settings.BASE_DIR)/'public/index.html').read_text().replace('data-mode="static"','data-mode="django"'))
def report(request):return JsonResponse(service.report())
def lab(request):return JsonResponse(exercise())
@require_POST
def run(request):
 if not request.user.is_authenticated or not request.user.is_staff:return JsonResponse({'error':'관리자 로그인 후 실행하세요.'},status=403)
 try:service.run_all()
 except service.Busy as e:return JsonResponse({'error':str(e)},status=409)
 return JsonResponse(service.report())
