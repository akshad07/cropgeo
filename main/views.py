from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.gis.geos import GEOSGeometry
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
import json
import httpx
import urllib.parse
from datetime import datetime as dt
from .models import User, Farm
from .forms import FarmForm
from .utils import get_stats, fetch_stats, get_imagery
from .enum import VegetationIndex, S2IndexFormulas
from . import weather_api as farm_weather

def dashboard(request):
    if not request.user.is_authenticated:
        return redirect('login')
    
    if not request.user.is_approved and not request.user.is_staff:
        messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
        return render(request, 'dashboard.html', {'pending_approval': True})
    
    farms = Farm.objects.filter(user=request.user)
    total_acres = sum(farm.size_acres for farm in farms if farm.size_acres) or 0
    context = {
        'farms': farms,
        'farms_count': farms.count(),
        'total_acres': total_acres,
    }
    return render(request, 'dashboard.html', context)

def login_view(request):
    if request.user.is_authenticated:
        # Redirect admin users to admin dashboard
        if request.user.is_staff:
            return redirect('admin_dashboard')
        return redirect('dashboard')
    
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        if not email or not password:
            messages.error(request, 'Please provide both email and password')
            return render(request, 'login.html')
        
        user = authenticate(request, username=email, password=password)
        if user:
            if not user.is_approved and not user.is_staff:
                messages.warning(request, 'Your account is pending approval. Please wait for admin approval.')
                return render(request, 'login.html')
            login(request, user)
            # Redirect admin users to admin dashboard
            if user.is_staff:
                return redirect('admin_dashboard')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid email or password')
    
    return render(request, 'login.html')

def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        age = request.POST.get('age')
        gender = request.POST.get('gender')
        password = request.POST.get('password')
        
        if not all([name, email, age, gender, password]):
            messages.error(request, 'Please fill in all fields')
            return render(request, 'signup.html')
        
        if User.objects.filter(username=email).exists():
            messages.error(request, 'Email already exists')
            return render(request, 'signup.html')
        
        try:
            user = User.objects.create_user(
                username=email,
                email=email,
                first_name=name,
                age=int(age),
                gender=gender,
                password=password,
                is_approved=False  # New users need admin approval
            )
            messages.success(request, 'Account created successfully! Please wait for admin approval.')
            return redirect('login')
        except Exception as e:
            messages.error(request, f'Error creating account: {str(e)}')
    
    return render(request, 'signup.html')

def about_view(request):
    return render(request, 'about.html')

@login_required
def add_farm_view(request):
    if not request.user.is_approved and not request.user.is_staff:
        messages.error(request, 'Your account must be approved to add farms.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
            
            farm_name = data.get('farmName')
            crop_type = data.get('cropType')
            farm_size = data.get('farmSize')
            geometry_data = data.get('geometry')
            
            if not all([farm_name, crop_type]):
                return JsonResponse({'success': False, 'error': 'Farm name and crop type are required'}, status=400)
            
            if not geometry_data:
                return JsonResponse({'success': False, 'error': 'Please draw the farm boundary on the map'}, status=400)
            
            # Parse geometry from GeoJSON
            try:
                if isinstance(geometry_data, str):
                    geom_dict = json.loads(geometry_data)
                else:
                    geom_dict = geometry_data
                
                # Validate GeoJSON structure
                if not isinstance(geom_dict, dict):
                    return JsonResponse({'success': False, 'error': 'Invalid geometry format'}, status=400)
                
                # Ensure it's a valid GeoJSON geometry
                if 'type' not in geom_dict or 'coordinates' not in geom_dict:
                    return JsonResponse({'success': False, 'error': 'Invalid GeoJSON structure'}, status=400)
                
                # Create GEOSGeometry from GeoJSON string
                # GEOSGeometry expects a GeoJSON string, not a dict
                geom_json_str = json.dumps(geom_dict)
                geom = GEOSGeometry(geom_json_str, srid=4326)
                
                # Validate the geometry
                if not geom or geom.empty:
                    return JsonResponse({'success': False, 'error': 'Empty or invalid geometry'}, status=400)
                    
            except json.JSONDecodeError as e:
                return JsonResponse({'success': False, 'error': f'Invalid JSON: {str(e)}'}, status=400)
            except Exception as e:
                return JsonResponse({'success': False, 'error': f'Invalid geometry: {str(e)}'}, status=400)
            
            # Create farm
            farm = Farm.objects.create(
                name=farm_name,
                crop_type=crop_type,
                size_acres=float(farm_size) if farm_size else None,
                geometry=geom,
                user=request.user
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Farm "{farm_name}" has been successfully added!',
                'farm_id': str(farm.id)
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    return render(request, 'add-farm.html')

def _elided_page_numbers(paginator, page_number):
    """Safe elided range for pagination controls (Django 4.1+)."""
    try:
        return list(
            paginator.get_elided_page_range(page_number, on_each_side=1, on_ends=1)
        )
    except (TypeError, ValueError):
        return list(paginator.page_range)


@user_passes_test(lambda u: u.is_staff)
def admin_dashboard_view(request):
    q = (request.GET.get('q') or '').strip()
    per_page = 10

    pending_base = User.objects.filter(is_approved=False, is_staff=False).order_by(
        '-date_joined'
    )
    approved_base = User.objects.filter(is_approved=True, is_staff=False).order_by(
        '-date_joined'
    )

    if q:
        name_q = (
            Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )
        pending_base = pending_base.filter(name_q)
        approved_base = approved_base.filter(name_q)

    pending_paginator = Paginator(pending_base, per_page)
    users_paginator = Paginator(approved_base, per_page)

    pending_page = pending_paginator.get_page(request.GET.get('pending_page') or 1)
    users_page = users_paginator.get_page(request.GET.get('users_page') or 1)

    all_farms = Farm.objects.all()
    pending_total = User.objects.filter(is_approved=False, is_staff=False).count()
    approved_total = User.objects.filter(is_approved=True, is_staff=False).count()

    context = {
        'pending_users': pending_page,
        'approved_users': users_page,
        'users_page': users_page,
        'pending_page': pending_page,
        'users_elided': _elided_page_numbers(users_paginator, users_page.number),
        'pending_elided': _elided_page_numbers(pending_paginator, pending_page.number),
        'page_ellipsis': Paginator.ELLIPSIS,
        'q': q,
        'all_farms': all_farms,
        'pending_count': pending_total,
        'approved_count': approved_total,
        'farms_count': all_farms.count(),
    }
    return render(request, 'admin-dashboard.html', context)

@user_passes_test(lambda u: u.is_staff)
def approve_user_view(request, user_id):
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        user.is_approved = True
        user.is_active = True  # Also activate the user
        user.save()
        messages.success(request, f'User {user.email} has been approved and activated.')
    return redirect('admin_dashboard')

@user_passes_test(lambda u: u.is_staff)
def reject_user_view(request, user_id):
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        # Don't allow rejecting staff users
        if user.is_staff:
            messages.error(request, 'Cannot reject staff users.')
            return redirect('admin_dashboard')
        user_email = user.email
        user.delete()
        messages.success(request, f'User {user_email} has been rejected and removed.')
    return redirect('admin_dashboard')

@user_passes_test(lambda u: u.is_staff)
def deactivate_user_view(request, user_id):
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        # Don't allow deactivating staff users
        if user.is_staff:
            messages.error(request, 'Cannot deactivate staff users.')
            return redirect('admin_dashboard')
        user.is_active = False
        user.save()
        messages.success(request, f'User {user.email} has been deactivated.')
    return redirect('admin_dashboard')

@user_passes_test(lambda u: u.is_staff)
def delete_user_view(request, user_id):
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        # Don't allow deleting staff users
        if user.is_staff:
            messages.error(request, 'Cannot delete staff users.')
            return redirect('admin_dashboard')
        user_email = user.email
        user.delete()
        messages.success(request, f'User {user_email} has been deleted successfully.')
    return redirect('admin_dashboard')

@login_required
def delete_farm_view(request, farm_id):
    if request.method == 'POST':
        farm = get_object_or_404(Farm, id=farm_id, user=request.user)
        farm_name = farm.name
        farm.delete()
        messages.success(request, f'Farm "{farm_name}" has been deleted successfully.')
    return redirect('dashboard')

@login_required
def view_farm_dashboard(request, farm_id):
    farm = get_object_or_404(Farm, id=farm_id, user=request.user)
    
    # Serialize geometry to GeoJSON for JavaScript
    farm_geojson = None
    farm_center = None
    if farm.geometry:
        # Get GeoJSON as a Feature (not just geometry) for proper OpenLayers loading
        from django.contrib.gis.geos import GEOSGeometry
        geojson_str = farm.geometry.geojson
        # Parse and create a Feature with the geometry
        import json
        geom_dict = json.loads(geojson_str)
        # Create a GeoJSON Feature
        farm_geojson = json.dumps({
            "type": "Feature",
            "geometry": geom_dict,
            "properties": {}
        })
        # Get center coordinates for map view
        centroid = farm.geometry.centroid
        farm_center = [centroid.x, centroid.y]  # [lon, lat]
    
    context = {
        'farm': farm,
        'farm_geojson': farm_geojson,
        'farm_center': farm_center,
    }
    return render(request, 'view-farm-dashboard.html', context)


@login_required
def farm_weather_current(request, farm_id):
    """JSON: current weather at farm centroid (Open-Meteo)."""
    farm = get_object_or_404(Farm, id=farm_id, user=request.user)
    if not farm.geometry:
        return JsonResponse({'error': 'Farm has no geometry'}, status=400)
    data, status_code = farm_weather.get_current_weather_payload(farm)
    return JsonResponse(data, status=status_code)


@login_required
def farm_weather_forecast(request, farm_id):
    """JSON: daily forecast (~16 days) at farm centroid (Open-Meteo)."""
    farm = get_object_or_404(Farm, id=farm_id, user=request.user)
    if not farm.geometry:
        return JsonResponse({'error': 'Farm has no geometry'}, status=400)
    data, status_code = farm_weather.get_forecast_weather_payload(farm)
    return JsonResponse(data, status=status_code)


@login_required
def search_satellite_data(request, farm_id):
    """Search for available Sentinel-2 data for a farm"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    farm = get_object_or_404(Farm, id=farm_id, user=request.user)
    
    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        cloud_cover = float(data.get('cloud_cover', 20))
        
        if not all([start_date, end_date]):
            return JsonResponse({'error': 'start_date and end_date are required'}, status=400)
        
        # Validate dates
        try:
            start_dt = dt.strptime(start_date, '%Y-%m-%d')
            end_dt = dt.strptime(end_date, '%Y-%m-%d')
            if end_dt < start_dt:
                return JsonResponse({'error': 'End date cannot be before start date'}, status=400)
            start_date_str = start_dt.strftime('%Y-%m-%d')
            end_date_str = end_dt.strftime('%Y-%m-%d')
        except ValueError:
            return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
        
        # Get farm geometry as GeoJSON
        if not farm.geometry:
            return JsonResponse({'error': 'Farm has no geometry'}, status=400)
        
        geojson_str = urllib.parse.quote(farm.geometry.geojson)
        
        # Search Element84 STAC API
        url = f"https://earth-search.aws.element84.com/v1/search?datetime={start_date_str}T00%3A00%3A00.000Z%2F{end_date_str}T23%3A59%3A59.000Z&limit=200&collections=sentinel-2-l2a&intersects={geojson_str}&query=%7B%22eo%3Acloud_cover%22%3A%7B%22gte%22%3A0%2C%22lte%22%3A{cloud_cover}%7D%7D"
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        response = httpx.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            return JsonResponse({'error': f'Error fetching data from STAC API: {response.text}'}, status=500)
        
        features = response.json().get('features', [])
        results = []
        for feature in features:
            properties = feature.get('properties', {})
            cloud_cover_val = properties.get('eo:cloud_cover', None)
            if cloud_cover_val is not None:
                cloud_cover_val = round(cloud_cover_val, 2)
            platform = properties.get('platform', 'Sentinel-2')
            datetime_str = properties.get('datetime', '')
            date = datetime_str[:10] if datetime_str else ''
            
            results.append({
                'id': feature.get('id', ''),
                'date': date,
                'cloud_cover': cloud_cover_val,
                'platform': platform,
            })
        
        return JsonResponse({
            'success': True,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_farm_stats(request, farm_id):
    """Get statistics for a specific date and index"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    farm = get_object_or_404(Farm, id=farm_id, user=request.user)
    
    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        item_id = data.get('item_id')
        index_type = data.get('index_type', 'ndvi')
        
        if not item_id:
            return JsonResponse({'error': 'item_id is required'}, status=400)
        
        # Validate index
        try:
            index = VegetationIndex(index_type)
            index_formula = S2IndexFormulas.get_formula(index)
            if not index_formula:
                return JsonResponse({'error': f'Invalid index type: {index_type}'}, status=400)
        except ValueError:
            return JsonResponse({'error': f'Invalid index type: {index_type}'}, status=400)
        
        # Get farm geometry
        if not farm.geometry:
            return JsonResponse({'error': 'Farm has no geometry'}, status=400)
        
        geometry_dict = json.loads(farm.geometry.geojson)
        
        # Prepare item data
        item = {
            'id': item_id,
            'date': data.get('date', ''),
            'platform': data.get('platform', 'Sentinel-2'),
            'cloud_cover': data.get('cloud_cover')
        }
        print(f"Fetching stats for item: {item}, index: {index_type}")
        # Get stats
        expression = urllib.parse.quote(index_formula.formula)
        # expression = index_formula.formula
        print(f"Using expression: {expression}")
        print(f"Using geometry: {geometry_dict}")
        stats_result = fetch_stats(item, 'sentinel-2-l2a', expression, geometry_dict)
        
        print(f"Stats result: {stats_result}")
        if stats_result:
            return JsonResponse({
                'success': True,
                'stats': {
                    'min': stats_result.get('min'),
                    'max': stats_result.get('max'),
                    'mean': stats_result.get('mean'),
                    'std': stats_result.get('std'),
                    'median': stats_result.get('median', stats_result.get('mean'))
                },
                'index_info': {
                    'name': index_formula.name,
                    'description': index_formula.description,
                    'value_range': [index_formula.min_value, index_formula.max_value]
                }
            })
        else:
            return JsonResponse({'error': 'Failed to fetch statistics'}, status=500)
            
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_farm_imagery(request, farm_id):
    """Get satellite imagery for a specific farm, date, and index"""
    farm = get_object_or_404(Farm, id=farm_id, user=request.user)
    
    try:
        # Get parameters from query string or request body
        if request.method == 'GET':
            item_id = request.GET.get('item_id')
            index_type = request.GET.get('index_type', 'ndvi')
            image_type = request.GET.get('image_type', 'png')
            colormap = request.GET.get('colormap')
            min_val = request.GET.get('min_val')
            max_val = request.GET.get('max_val')
            pixelized = request.GET.get('pixelized', 'false').lower() == 'true'
        else:
            data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
            item_id = data.get('item_id')
            index_type = data.get('index_type', 'ndvi')
            image_type = data.get('image_type', 'png')
            colormap = data.get('colormap')
            min_val = data.get('min_val')
            max_val = data.get('max_val')
            pixelized = data.get('pixelized', False)
        
        if not item_id:
            return JsonResponse({'error': 'item_id is required'}, status=400)
        
        # Validate image type
        if image_type not in ['png', 'jpeg', 'tif']:
            return JsonResponse({'error': f'Invalid image type. Must be one of: png, jpeg, tif'}, status=400)
        
        # Validate index
        try:
            index = VegetationIndex(index_type)
            index_formula = S2IndexFormulas.get_formula(index)
            if not index_formula:
                return JsonResponse({'error': f'Invalid index type: {index_type}'}, status=400)
        except ValueError:
            return JsonResponse({'error': f'Invalid index type: {index_type}'}, status=400)
        
        # Get farm geometry
        if not farm.geometry:
            return JsonResponse({'error': 'Farm has no geometry'}, status=400)
        
        geometry_dict = json.loads(farm.geometry.geojson)
        
        # Prepare parameters - match oed implementation
        max_value = float(max_val) if max_val else index_formula.max_value
        min_value = float(min_val) if min_val else index_formula.min_value
        formula = index_formula.formula
        
        # Get colormap
        colormap_name = colormap if colormap else index_formula.colormap
        
        # Get imagery using utils function - match oed exactly
        try:
            import base64 as base64_module
            
            # Match oed: for RGB use formula as-is, for others URL encode it
            if index_type == "rgb":
                final_expression = formula
            else:
                final_expression = urllib.parse.quote(formula)
            
            # Call get_imagery from utils
            # Get required bands from index formula for assets parameter
            required_bands = index_formula.bands if hasattr(index_formula, 'bands') and index_formula.bands else None
            
            result = get_imagery(
                collection="sentinel-2-l2a",
                expression=final_expression,
                colormap=colormap_name,
                rescale=f"{min_value},{max_value}",
                response_format=image_type,
                item_id=item_id,
                geometry=geometry_dict,
                pixelized=pixelized,
                required_bands=required_bands
            )
            
            # Extract base64 image from response
            if image_type == 'png' or image_type == 'jpeg':
                # The result is an HttpResponse with base64 data URL
                image_data = result.content.decode('utf-8')
                # Extract base64 part (remove "data:image/png;base64," prefix if present)
                if image_data.startswith('data:image'):
                    base64_image = image_data.split(',')[1] if ',' in image_data else image_data
                    image_data_url = image_data  # Keep the full data URL
                else:
                    base64_image = image_data
                    image_data_url = f"data:image/{image_type};base64,{base64_image}"
            else:
                # For TIFF, convert to base64
                image_base64 = base64_module.b64encode(result.content).decode('utf-8')
                image_data_url = f"data:image/{image_type};base64,{image_base64}"
            
            # Get bbox from farm geometry
            bbox = farm.geometry.extent  # Returns [minx, miny, maxx, maxy]
            
            # Return JSON with image and bbox
            return JsonResponse({
                'success': True,
                'image': image_data_url,
                'bbox': bbox,  # [minx, miny, maxx, maxy]
                'format': image_type
            })
        except Exception as e:
            import traceback
            return JsonResponse({'error': f'Failed to fetch imagery: {str(e)}', 'traceback': traceback.format_exc()}, status=500)
            
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def logout_view(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')
