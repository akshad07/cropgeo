import pystac_client
import httpx
from django.http import HttpResponse, StreamingHttpResponse
from django.core.exceptions import ValidationError
from io import BytesIO
import base64
import json

# import TITILER_URL from settings 
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.conf import settings


titiler_url = settings.TITILER_URL if hasattr(settings, 'TITILER_URL') else 'https://titiler.vistamap.co'
# Ensure URL doesn't have trailing slash
if titiler_url and titiler_url.endswith('/'):
    titiler_url = titiler_url.rstrip('/')

def get_imagery(collection, expression, colormap, rescale, response_format, item_id, geometry, pixelized=False, required_bands=None):
    # Match oed implementation, but add assets if required_bands provided (for local Titiler compatibility)
    if expression == "red,green,blue":
        assets_param = "&assets=red&assets=green&assets=blue"
    else:
        # For expressions, use expression parameter
        # If required_bands is provided, also include assets (for local Titiler that requires assets)
        if required_bands and len(required_bands) > 0:
            assets_list = "&" + "&".join([f"assets={band}" for band in required_bands])
            assets_param = f"{assets_list}&expression={expression}"
        else:
            # Original oed implementation - expression only
            assets_param = f"expression={expression}"

    if (collection == 'cop-dem-glo-30'):
        url = f"{titiler_url}/stac/feature.{response_format}?url=https://earth-search.aws.element84.com/v1/collections/{collection}/items/{item_id}&{assets_param}&asset_as_band=True&algorithm=hillshade"
        if response_format in ['png']:
            if colormap:
                url += f"&colormap_name={colormap.lower()}"
    else:
        url = f"{titiler_url}/stac/feature.{response_format}?url=https://earth-search.aws.element84.com/v1/collections/{collection}/items/{item_id}&{assets_param}&asset_as_band=True"
        print("pixelized =", pixelized)
        if pixelized:
            print("pixelized")
            url += "&resampling=nearest&reproject=nearest"
        else:
            print("not pixelized")
            url += "&resampling=gauss&reproject=cubic"
        if response_format in ['png']:
            url += f"&height=1500&width=1500&rescale={rescale}"
            if colormap:
                url += f"&colormap_name={colormap.lower()}"
    # print(url)
        
        
    payload = {
        "type": "Feature",
        "geometry": geometry,"properties": {},
        "id": 0
    }
    # print(payload)

    headers = {
        "accept": f"image/{response_format}",
        "Content-Type": "application/json"
    }
    with httpx.Client(timeout=300) as client:
        response =  client.post(url, headers=headers, json=payload)
        
    if response.status_code != 200:
        raise ValidationError(f"Failed to fetch imagery: {response.status_code}, {response.text}")

        
    if response_format == 'png':
        # print('Converting to base64')
        image_base64 = base64.b64encode(response.content).decode('utf-8')
        return HttpResponse(
            f"data:image/png;base64,{image_base64}",
            content_type="text/plain"
        )
    else:
        # print('Returning TIFF')
        return StreamingHttpResponse(
            BytesIO(response.content),
            content_type=f"image/tiff"
        )


def get_raw_band_data(collection, band, item_id, geometry):
    """
    Get raw band data for a specific item in a STAC collection.
    
    Args:
        collection (str): The STAC collection name.
        band (str): The band to retrieve (e.g., 'B04' for Sentinel-2 red band).
        item_id (str): The STAC item ID.
        geometry (dict): Geometry for the item.
    
    Returns:
        StreamingHttpResponse: A streaming response containing the raw TIFF data.
    """
    if not titiler_url:
        raise ValidationError("TITILER_URL is not configured")
    
    url = f"{titiler_url}/stac/feature.tif?url=https://earth-search.aws.element84.com/v1/collections/{collection}/items/{item_id}&assets={band}&asset_as_band=True&return_mask=true&resampling=gauss&reproject=cubic"
    
    # print(f"Fetching raw band data: {url}")
    
    payload = {
        "type": "Feature",
        "geometry": geometry,
        "properties": {},
        "id": 0
    }
    
    headers = {
        "accept": "image/tiff",
        "Content-Type": "application/json"
    }
    
    with httpx.Client(timeout=300) as client:
        response = client.post(url, headers=headers, json=payload)
        
    if response.status_code != 200:
        raise ValidationError(f"Failed to fetch raw band data: {response.text}")
        
    return StreamingHttpResponse(
        BytesIO(response.content),
        content_type="image/tiff"
    )


def fetch_stats(item, collection, expression, geometry):
    payload = {
        "type": "Feature",
        "geometry": geometry,
        "properties": {},
        "id": 0
    }

    stats_url = (
        f"{titiler_url}/stac/statistics?url=https://earth-search.aws.element84.com/v1/collections/{collection}/items/{item['id']}&"
        f"expression={expression}&asset_as_band=True"
    )

    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json'
    }
    print(f"Fetching stats for item {item['id']} with URL: {stats_url}")
    print(f"Payload: {payload}")
    try:
        with httpx.Client(timeout=300) as client:
            response = client.post(stats_url, headers=headers, json=payload)
            res_response = response.json()
            print(f"Stats response for item {item['id']}: {res_response}")
            
            stats_key = next(iter(res_response['properties']['statistics']))
            stats = res_response['properties']['statistics'][stats_key]

            entry = {
                "date": item["date"],
                "item_id": item["id"],
                "collection": collection,
                "platform": item["platform"],
                "min": stats['min'],
                "max": stats['max'],
                "mean": stats['mean'],
                "std": stats['std']
            }

            cloud_cover = item.get('cloud_cover')
            if cloud_cover is not None:
                entry["cloud_cover"] = cloud_cover

            return entry

    except Exception as e:
        print(f"Error processing item {item['id']}: {e}")
        return None


def get_stats(items, collection, expression, geometry, max_workers=10):
    """
    Get statistics for a list of items using multi-threading.

    Args:
        items (list): List of STAC items.
        collection (str): Collection name.
        expression (str): Expression to evaluate.
        geometry (dict): Geometry to apply.
        max_workers (int): Number of threads.

    Returns:
        list: List of statistics dictionaries.
    """
    all_stats = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(fetch_stats, item, collection, expression, geometry)
            for item in items
        ]

        for future in as_completed(futures):
            result = future.result()
            if result:
                all_stats.append(result)

    return all_stats

