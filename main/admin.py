from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Farm


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'is_approved', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_approved', 'is_staff', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'first_name')
    fieldsets = UserAdmin.fieldsets + (
        ('Additional Info', {'fields': ('age', 'gender', 'is_approved')}),
    )


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ('name', 'crop_type', 'size_acres', 'user', 'created_at')
    list_filter = ('crop_type', 'created_at')
    search_fields = ('name', 'user__username', 'user__email')
    readonly_fields = ('id', 'area', 'created_at', 'updated_at')
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'name', 'user', 'crop_type', 'size_acres')
        }),
        ('Geographic Data', {
            'fields': ('geometry', 'area')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

