from django.contrib.auth.models import AbstractUser
from django.contrib.gis.db import models
from django.utils import timezone
from django.contrib.gis.geos import GEOSGeometry
import uuid

class User(AbstractUser):
    age = models.PositiveIntegerField(default=18)
    gender = models.CharField(max_length=20, choices=[
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
        ('prefer-not-to-say', 'Prefer not to say'),
    ], default='prefer-not-to-say')
    is_approved = models.BooleanField(default=False)

class Farm(models.Model):
    """
    Model to store farm information with geographic boundaries.
    Based on Geometry template from oed/stac/models.py
    """
    CROP_TYPE_CHOICES = [
        ('wheat', 'Wheat'),
        ('corn', 'Corn'),
        ('soybeans', 'Soybeans'),
        ('rice', 'Rice'),
        ('cotton', 'Cotton'),
        ('barley', 'Barley'),
        ('oats', 'Oats'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    crop_type = models.CharField(max_length=50, choices=CROP_TYPE_CHOICES)
    size_acres = models.FloatField(null=True, blank=True)
    geometry = models.GeometryField(srid=4326)
    area = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='farms')
    
    def save(self, *args, **kwargs):
        if self.geometry and self.geometry.srid == 4326:
            lon = self.geometry.centroid.x
            utm_zone = int((lon + 180) / 6) + 1
            utm_srid = 32600 + utm_zone  # Northern Hemisphere UTM
            transformed_geom = self.geometry.transform(utm_srid, clone=True)
            self.area = transformed_geom.area
            # Convert square meters to acres
            if self.area:
                self.size_acres = self.area * 0.000247105
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.id})"

    class Meta:
        verbose_name = "Farm"
        verbose_name_plural = "Farms"
        ordering = ['-created_at']
