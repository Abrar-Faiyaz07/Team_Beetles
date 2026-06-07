from django.db import models

class Application(models.Model):
    STATUS_CHOICES = [
        ('applied', 'Applied'),
        ('interviewing', 'Interviewing'),
        ('offer', 'Offer'),
        ('rejected', 'Rejected'),
    ]
    user_id = models.CharField(max_length=255)
    company = models.CharField(max_length=255)
    role = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='applied')
    applied_date = models.DateField(auto_now_add=True)

class Goal(models.Model):
    user_id = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    deadline = models.DateField()
    is_completed = models.BooleanField(default=False)
