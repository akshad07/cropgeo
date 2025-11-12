from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    age = models.PositiveIntegerField(default=18)
    gender = models.CharField(max_length=20, choices=[
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
        ('prefer-not-to-say', 'Prefer not to say'),
    ], default='prefer-not-to-say')
