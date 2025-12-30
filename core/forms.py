from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from .models import Note, Profile, Comment

class UserRegisterForm(UserCreationForm):
    # --- STRICT TEXT LIMITS ---
    first_name = forms.CharField(max_length=20, required=False, 
                               widget=forms.TextInput(attrs={'placeholder': 'Max 20 chars', 'maxlength': '20'}))
    last_name = forms.CharField(max_length=20, required=False, 
                              widget=forms.TextInput(attrs={'placeholder': 'Max 20 chars', 'maxlength': '20'}))
    email = forms.EmailField(required=True, max_length=100, 
                           widget=forms.EmailInput(attrs={'maxlength': '100'}))

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email']

    def clean_username(self):
        username = self.cleaned_data.get('username')
        # 1. Length Check
        if len(username) > 15:
            raise ValidationError("Username must be 15 characters or fewer.")
        # 2. Content Check (Optional: Alphanumeric only)
        if not username.isalnum() and "_" not in username:
             raise ValidationError("Username can only contain letters, numbers, and underscores.")
        return username

class ProfileForm(forms.ModelForm):
    # --- STRICT TEXT LIMITS ---
    # Overriding model fields to enforce limits at form level
    bio = forms.CharField(required=False, max_length=300, 
                        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'maxlength': '300'}))
    ai_instructions = forms.CharField(required=False, max_length=500, 
                                    widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'maxlength': '500'}))

    class Meta:
        model = Profile
        fields = ['bio', 'profile_pic', 'ai_instructions'] # Added ai_instructions here
        widgets = {
            'profile_pic': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }

    # 5MB Image Limit
    def clean_profile_pic(self):
        pic = self.cleaned_data.get('profile_pic')
        if pic:
            if pic.size > 5 * 1024 * 1024:
                raise ValidationError("Image too large. Max size is 5MB.")
            if not pic.content_type.startswith('image/'):
                raise ValidationError("Invalid file. Please upload an image.")
        return pic

class NoteForm(forms.ModelForm):
    # --- STRICT TEXT LIMITS ---
    title = forms.CharField(max_length=60, widget=forms.TextInput(attrs={'class': 'form-control', 'maxlength': '60'}))
    course = forms.CharField(required=False, max_length=30, widget=forms.TextInput(attrs={'class': 'form-control', 'maxlength': '30'}))
    tags = forms.CharField(required=False, max_length=50, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'math, science', 'maxlength': '50'}))
    
    # Description is a TextField in DB, but we limit it to 1000 chars here
    description = forms.CharField(required=False, max_length=1000, 
                                widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control', 'maxlength': '1000'}))

    class Meta:
        model = Note
        fields = ['title', 'course', 'description', 'tags', 'file']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control'}),
        }

    # 35MB File Limit
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            if file.size > 35 * 1024 * 1024:
                raise ValidationError("File too large. Max size is 35MB.")
        return file

class CommentForm(forms.ModelForm):
    # --- STRICT TEXT LIMITS ---
    text = forms.CharField(max_length=500, widget=forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 2, 
                'placeholder': 'Add a comment...',
                'maxlength': '500' 
            }))

    class Meta:
        model = Comment
        fields = ['text']