from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .models import User

def dashboard(request):
    if not request.user.is_authenticated:
        return redirect('login')
    return render(request, 'dashboard.html')

def login_view(request):
    if request.method == 'POST':
        email = request.POST['email']
        password = request.POST['password']
        user = authenticate(request, username=email, password=password)
        if user:
            login(request, user)
            return redirect('dashboard')
        messages.error(request, 'Invalid email or password')
    return render(request, 'login.html')

def signup_view(request):
    if request.method == 'POST':
        name = request.POST['name']
        email = request.POST['email']
        age = request.POST['age']
        gender = request.POST['gender']
        password = request.POST['password']
        
        if User.objects.filter(username=email).exists():
            messages.error(request, 'Email already exists')
        else:
            user = User.objects.create_user(
                username=email,
                email=email,
                first_name=name,
                age=age,
                gender=gender,
                password=password
            )
            login(request, user)
            return redirect('dashboard')
    return render(request, 'signup.html')

def about_view(request):
    return render(request, 'about.html')

def add_farm_view(request):
    return render(request, 'add-farm.html')

def admin_dashboard_view(request):
    return render(request, 'admin-dashboard.html')

def view_farm_dashboard(request):
    return render(request, 'view-farm-dashboard.html')

def logout_view(request):
    logout(request)
    return redirect('login')
