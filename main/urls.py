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
    path('approve-user/<int:user_id>/', views.approve_user_view, name='approve_user'),
    path('reject-user/<int:user_id>/', views.reject_user_view, name='reject_user'),
    path('deactivate-user/<int:user_id>/', views.deactivate_user_view, name='deactivate_user'),
    path('delete-user/<int:user_id>/', views.delete_user_view, name='delete_user'),
    path('view-farm/<uuid:farm_id>/', views.view_farm_dashboard, name='view_farm'),
    path('delete-farm/<uuid:farm_id>/', views.delete_farm_view, name='delete_farm'),
    path('farm/<uuid:farm_id>/search-satellite/', views.search_satellite_data, name='search_satellite_data'),
    path('farm/<uuid:farm_id>/get-stats/', views.get_farm_stats, name='get_farm_stats'),
    path('farm/<uuid:farm_id>/get-imagery/', views.get_farm_imagery, name='get_farm_imagery'),
    path('farm/<uuid:farm_id>/weather/current/', views.farm_weather_current, name='farm_weather_current'),
    path('farm/<uuid:farm_id>/weather/forecast/', views.farm_weather_forecast, name='farm_weather_forecast'),
]