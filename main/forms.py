from django import forms
from django.contrib.gis.geos import GEOSGeometry
from .models import Farm, User

class FarmForm(forms.ModelForm):
    farmName = forms.CharField(max_length=255, label='Farm Name')
    cropType = forms.ChoiceField(choices=Farm.CROP_TYPE_CHOICES, label='Crop Type')
    farmSize = forms.FloatField(required=False, label='Size (acres)')
    geometry = forms.CharField(widget=forms.HiddenInput(), required=False)
    
    class Meta:
        model = Farm
        fields = ['name', 'crop_type', 'size_acres', 'geometry']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['farmName'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Enter farm name'})
        self.fields['cropType'].widget.attrs.update({'class': 'form-control'})
        self.fields['farmSize'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Enter size in acres'})
    
    def clean(self):
        cleaned_data = super().clean()
        farm_name = cleaned_data.get('farmName')
        crop_type = cleaned_data.get('cropType')
        geometry_str = cleaned_data.get('geometry')
        
        if farm_name:
            cleaned_data['name'] = farm_name
        if crop_type:
            cleaned_data['crop_type'] = crop_type
        
        # Parse geometry from GeoJSON string if provided
        if geometry_str:
            try:
                import json
                geom_data = json.loads(geometry_str)
                if geom_data.get('type') == 'Polygon':
                    coordinates = geom_data.get('coordinates', [])
                    if coordinates:
                        # Convert GeoJSON coordinates to GEOSGeometry
                        # GeoJSON is [lon, lat], GEOSGeometry expects (lon, lat)
                        geom = GEOSGeometry(json.dumps(geom_data), srid=4326)
                        cleaned_data['geometry'] = geom
            except (json.JSONDecodeError, Exception) as e:
                raise forms.ValidationError(f"Invalid geometry data: {str(e)}")
        
        return cleaned_data
