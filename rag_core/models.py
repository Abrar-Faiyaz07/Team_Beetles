from django.db import models

class UserProfile(models.Model):
    user_id = models.CharField(max_length=255, unique=True)
    cv_file = models.FileField(upload_to='cvs/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_processed = models.BooleanField(default=False)

    def __str__(self):
        return self.user_id
