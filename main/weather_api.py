"""
Open-Meteo helpers for farm dashboards (centroid of farm.geometry).
Used by session-authenticated JSON views in views.py — no DRF.
"""
import datetime
from datetime import timedelta

import httpx


def _farm_lat_lon(farm):
    c = farm.geometry.centroid
    return c.y, c.x


def get_current_weather_payload(farm):
    """
    Build current-weather dict for JsonResponse (same field names as former APIView).
    Returns (payload_dict, http_status).
    """
    lat, lon = _farm_lat_lon(farm)
    url = 'https://api.open-meteo.com/v1/forecast'
    params = {
        'latitude': lat,
        'longitude': lon,
        'current': (
            'relative_humidity_2m,apparent_temperature,precipitation,rain,cloud_cover,'
            'surface_pressure,wind_speed_10m,wind_gusts_10m,temperature_2m,'
            'soil_temperature_0cm,soil_temperature_6cm,soil_temperature_18cm,soil_temperature_54cm,'
            'soil_moisture_0_to_1cm,soil_moisture_1_to_3cm,soil_moisture_3_to_9cm,'
            'soil_moisture_9_to_27cm,soil_moisture_27_to_81cm'
        ),
        'daily': (
            'apparent_temperature_max,apparent_temperature_min,sunrise,sunset,'
            'uv_index_max,et0_fao_evapotranspiration'
        ),
        'timezone': 'GMT',
        'forecast_days': 1,
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.get(url, params=params)
        if r.status_code != 200:
            return {'error': 'Upstream error', 'detail': r.text[:500]}, 502
        response = r.json()

    for key in (
        'generationtime_ms',
        'utc_offset_seconds',
        'latitude',
        'longitude',
        'timezone_abbreviation',
        'current_units',
        'daily_units',
    ):
        response.pop(key, None)

    response['current']['temp'] = response['current'].pop('temperature_2m')
    response['current']['relative_humidity'] = response['current'].pop('relative_humidity_2m')
    response['current']['wind_speed'] = response['current'].pop('wind_speed_10m')
    response['current']['wind_gusts'] = response['current'].pop('wind_gusts_10m')
    daily = response['daily']
    response['current']['apparent_temperature_max'] = daily['apparent_temperature_max'][0]
    response['current']['apparent_temperature_min'] = daily['apparent_temperature_min'][0]
    response['current']['sunrise'] = daily['sunrise'][0]
    response['current']['sunset'] = daily['sunset'][0]
    response['current']['uv_index_max'] = daily['uv_index_max'][0]
    response['current']['et0_fao_evapotranspiration'] = daily['et0_fao_evapotranspiration'][0]
    response['current']['soil_temperature_surface'] = response['current'].pop('soil_temperature_0cm')
    response['current']['soil_temperature_5cm'] = response['current'].pop('soil_temperature_6cm')
    response['current']['soil_temperature_15cm'] = response['current'].pop('soil_temperature_18cm')
    response['current']['soil_temperature_60cm'] = response['current'].pop('soil_temperature_54cm')
    response['current']['soil_moisture_surface'] = response['current'].pop('soil_moisture_0_to_1cm')
    response['current']['soil_moisture_2cm'] = response['current'].pop('soil_moisture_1_to_3cm')
    response['current']['soil_moisture_5cm'] = response['current'].pop('soil_moisture_3_to_9cm')
    response['current']['soil_moisture_15cm'] = response['current'].pop('soil_moisture_9_to_27cm')
    response['current']['soil_moisture_50cm'] = response['current'].pop('soil_moisture_27_to_81cm')
    response.pop('daily', None)

    response['farm_id'] = str(farm.id)
    response['farm_name'] = farm.name
    response['units'] = {
        'time': 'iso8601',
        'interval': 's',
        'temp': '°C',
        'temperature': '°C',
        'relative_humidity': '%',
        'apparent_temperature': '°C',
        'precipitation': 'mm',
        'rain': 'mm',
        'cloud_cover': '%',
        'surface_pressure': 'hPa',
        'wind_speed': 'km/h',
        'wind_gusts': 'km/h',
        'apparent_temperature_max': '°C',
        'apparent_temperature_min': '°C',
        'sunrise': 'iso8601',
        'sunset': 'iso8601',
        'uv_index_max': '',
        'et0_fao_evapotranspiration': 'mm',
        'soil_temperature_surface': '°C',
        'soil_temperature_5cm': '°C',
        'soil_temperature_15cm': '°C',
        'soil_temperature_60cm': '°C',
        'soil_moisture_surface': 'm³/m³',
        'soil_moisture_2cm': 'm³/m³',
        'soil_moisture_5cm': 'm³/m³',
        'soil_moisture_15cm': 'm³/m³',
        'soil_moisture_50cm': 'm³/m³',
    }
    return response, 200


def get_forecast_weather_payload(farm):
    """
    Build daily forecast dict for JsonResponse (~16 days).
    Returns (payload_dict, http_status).
    """
    lat, lon = _farm_lat_lon(farm)
    forecast_url = 'https://api.open-meteo.com/v1/forecast'
    today = datetime.datetime.utcnow().date()
    end_date = today + timedelta(days=15)

    forecast_daily_variables = [
        'temperature_2m_max',
        'temperature_2m_min',
        'temperature_2m_mean',
        'relative_humidity_2m_max',
        'precipitation_sum',
        'rain_sum',
        'surface_pressure_mean',
        'cloud_cover_mean',
        'et0_fao_evapotranspiration',
        'wind_speed_10m_max',
        'wind_gusts_10m_max',
    ]

    forecast_base_params = {
        'latitude': lat,
        'longitude': lon,
        'timezone': 'GMT',
        'start_date': today.isoformat(),
        'end_date': end_date.isoformat(),
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            forecast_params_all = dict(forecast_base_params)
            forecast_params_all['daily'] = forecast_daily_variables
            forecast_response = client.get(forecast_url, params=forecast_params_all)

            if forecast_response.status_code == 200:
                forecast_data = forecast_response.json()
            else:
                combined_daily_forecast = {}
                time_series_forecast = None

                for i in range(0, len(forecast_daily_variables), 2):
                    chunk = forecast_daily_variables[i : i + 2]
                    chunk_params = dict(forecast_base_params)
                    chunk_params['daily'] = chunk
                    chunk_response = client.get(forecast_url, params=chunk_params)

                    if chunk_response.status_code == 200:
                        chunk_data = chunk_response.json()
                        daily_chunk = chunk_data.get('daily', {})
                        if 'time' in daily_chunk:
                            if time_series_forecast is None:
                                time_series_forecast = daily_chunk['time']
                                combined_daily_forecast['time'] = time_series_forecast
                        for key, value in daily_chunk.items():
                            if key == 'time':
                                continue
                            combined_daily_forecast[key] = value
                    else:
                        if time_series_forecast is None:
                            days = (end_date - today).days + 1
                            time_series_forecast = [
                                (today + timedelta(days=j)).isoformat() for j in range(days)
                            ]
                            combined_daily_forecast['time'] = time_series_forecast
                        days = len(time_series_forecast)
                        for var in chunk:
                            if var not in combined_daily_forecast:
                                combined_daily_forecast[var] = [None] * days

                forecast_data = {'daily': combined_daily_forecast}

            daily_data = forecast_data.get('daily', {})
            remap = {
                'time': 'time',
                'temperature_2m_max': 'temp_max',
                'temperature_2m_min': 'temp_min',
                'temperature_2m_mean': 'temp_mean',
                'relative_humidity_2m_max': 'relative_humidity',
                'precipitation_sum': 'precipitation',
                'rain_sum': 'rain',
                'surface_pressure_mean': 'surface_pressure',
                'cloud_cover_mean': 'cloud_cover',
                'et0_fao_evapotranspiration': 'evapotranspiration',
                'wind_speed_10m_max': 'wind_speed',
                'wind_gusts_10m_max': 'wind_gusts',
            }
            mapped_daily = {}
            for old_key, new_key in remap.items():
                if old_key in daily_data:
                    mapped_daily[new_key] = daily_data[old_key]

        result = {
            'farm_id': str(farm.id),
            'farm_name': farm.name,
            'forecast': mapped_daily,
            'units': {
                'time': 'iso8601',
                'temp_max': '°C',
                'temp_min': '°C',
                'temp_mean': '°C',
                'relative_humidity': '%',
                'precipitation': 'mm',
                'rain': 'mm',
                'surface_pressure': 'hPa',
                'cloud_cover': '%',
                'evapotranspiration': 'mm',
                'wind_speed': 'km/h',
                'wind_gusts': 'km/h',
            },
        }
        return result, 200

    except Exception as e:
        return {'error': 'Server error', 'detail': str(e)}, 500
