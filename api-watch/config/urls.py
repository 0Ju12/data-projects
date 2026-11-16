from django.contrib import admin
from django.urls import path
from watchtower import views
urlpatterns=[path('admin/',admin.site.urls),path('',views.dashboard),path('api/report',views.report),path('api/run',views.run),path('api/lab',views.lab),path('api/catalog',views.catalog)]
