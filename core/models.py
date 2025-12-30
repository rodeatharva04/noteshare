import os
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from PIL import Image
from .utils import delete_file_if_exists

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(blank=True)
    profile_pic = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    verification_code = models.CharField(max_length=6, blank=True, null=True)
    ai_instructions = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.user.username

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.profile_pic:
            try:
                img = Image.open(self.profile_pic.path)
                if img.height > 300 or img.width > 300:
                    output_size = (300, 300)
                    img.thumbnail(output_size)
                    img.save(self.profile_pic.path)
            except Exception as e:
                print(f"Error compressing image: {e}")

class Note(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    course = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True)
    tags = models.CharField(max_length=200, blank=True)
    file = models.FileField(upload_to='notes/')
    created_at = models.DateTimeField(auto_now_add=True)
    view_count = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['course']),
            models.Index(fields=['tags']),
        ]

    def __str__(self):
        return self.title

    def get_file_type(self):
        if not self.file:
            return 'none'
        
        _, ext = os.path.splitext(self.file.name)
        ext = ext.lower()

        if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp']:
            return 'image'
        elif ext in ['.mp4', '.webm', '.ogg', '.mov']:
            return 'video'
        elif ext in ['.mp3', '.wav']:
            return 'audio'
        elif ext == '.pdf':
            return 'pdf'
        elif ext in ['.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt']:
            return 'office'
        elif ext in [
            '.txt', '.md', '.csv', '.json', '.xml', '.log', 
            '.py', '.js', '.html', '.css', '.java', '.cpp', '.c', '.h', 
            '.sql', '.sh', '.bat', '.php', '.rb', '.go', '.rs', '.ts',
            '.yaml', '.yml', '.ini', '.conf', '.env'
        ]:
            return 'code'
        else:
            return 'other'
    
class Comment(models.Model):
    post = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

class Rating(models.Model):
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name='ratings')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    score = models.IntegerField(default=1)

    class Meta:
        unique_together = ('note', 'user')

@receiver(post_delete, sender=Note)
def auto_delete_note_file(sender, instance, **kwargs):
    delete_file_if_exists(instance.file)

@receiver(post_delete, sender=Profile)
def auto_delete_profile_pic(sender, instance, **kwargs):
    delete_file_if_exists(instance.profile_pic)

@receiver(pre_save, sender=Note)
def auto_delete_old_note_file_on_change(sender, instance, **kwargs):
    if not instance.pk: 
        return False 
    try:
        old_file = Note.objects.get(pk=instance.pk).file
        if old_file and old_file != instance.file:
            delete_file_if_exists(old_file)
    except Note.DoesNotExist: 
        pass

@receiver(pre_save, sender=Profile)
def auto_delete_old_profile_pic_on_change(sender, instance, **kwargs):
    if not instance.pk: 
        return False
    try:
        old_pic = Profile.objects.get(pk=instance.pk).profile_pic
        if old_pic and old_pic != instance.profile_pic:
            delete_file_if_exists(old_pic)
    except Profile.DoesNotExist: 
        pass
