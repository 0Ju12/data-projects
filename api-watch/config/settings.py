import os
from pathlib import Path
BASE_DIR=Path(__file__).resolve().parent.parent
SECRET_KEY=os.environ.get('DJANGO_SECRET_KEY','local-development-only-change-before-hosting')
DEBUG=os.environ.get('DJANGO_DEBUG','1')=='1'
if not DEBUG and (not SECRET_KEY or SECRET_KEY.startswith(('local-development','replace-','change-me'))):raise RuntimeError('Set DJANGO_SECRET_KEY for production.')
ALLOWED_HOSTS=[x.strip()for x in os.environ.get('DJANGO_ALLOWED_HOSTS','localhost,127.0.0.1,testserver').split(',')]
INSTALLED_APPS=['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','watchtower']
MIDDLEWARE=['django.middleware.security.SecurityMiddleware','whitenoise.middleware.WhiteNoiseMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF='config.urls';WSGI_APPLICATION='config.wsgi.application'
TEMPLATES=[{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
if os.environ.get('POSTGRES_HOST'):
 DATABASES={'default':{'ENGINE':'django.db.backends.postgresql','NAME':os.environ.get('POSTGRES_DB','api_watch'),'USER':os.environ.get('POSTGRES_USER','api_watch'),'PASSWORD':os.environ['POSTGRES_PASSWORD'],'HOST':os.environ['POSTGRES_HOST'],'PORT':os.environ.get('POSTGRES_PORT','5432')}}
else:DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':os.environ.get('MONITOR_DB',str(BASE_DIR/'monitor.sqlite3')),'OPTIONS':{'timeout':20}}}
LANGUAGE_CODE='ko-kr';TIME_ZONE='UTC';USE_TZ=True;STATIC_URL='/static/';STATIC_ROOT=BASE_DIR/'staticfiles';DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
SESSION_COOKIE_HTTPONLY=True;CSRF_COOKIE_HTTPONLY=False
if not DEBUG:SESSION_COOKIE_SECURE=os.environ.get('DJANGO_SECURE_COOKIES','1')=='1';CSRF_COOKIE_SECURE=SESSION_COOKIE_SECURE;SECURE_CONTENT_TYPE_NOSNIFF=True
LOGIN_URL='/admin/login/'
