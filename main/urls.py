from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('about/', views.about_view, name='about'),
    path('add-farm/', views.add_farm_view, name='add_farm'),
    path('admin-dashboard/', views.admin_dashboard_view, name='admin_dashboard'),
    path('view-farm/', views.view_farm_dashboard, name='view_farm'),
]