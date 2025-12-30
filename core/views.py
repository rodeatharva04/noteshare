import os
import json
import threading
import mimetypes
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.contrib import messages
from django.db.models import Avg, Count, Case, When, Value, IntegerField
from django.http import JsonResponse, FileResponse, Http404
from django.conf import settings
from django.template.loader import render_to_string

# Local imports
from .forms import UserRegisterForm, ProfileForm, NoteForm, CommentForm
from .models import Note, Profile, Comment, Rating
from .utils import send_email, generate_otp, delete_file_if_exists
from .gemini import generate_study_help

# ==========================
# SIGNALS & ALERTS
# ==========================
@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    """
    Sends an email alert when a user logs in.
    """
    try:
        # Run in a separate thread so login isn't slow
        threading.Thread(target=send_email, args=(
            user.email,
            "Security Alert: New Login",
            "New Sign-In Detected",
            f"We detected a new login to your account <b>{user.username}</b>.",
            user.username
        )).start()
    except Exception as e:
        print(f"Email Error: {e}")

# ==========================
# AUTHENTICATION
# ==========================

def register(request):
    if request.method == 'POST':
        # --- CLEANUP LOGIC ---
        # If a username/email is taken by an UNVERIFIED account, delete it so new user can claim it.
        username = request.POST.get('username')
        email = request.POST.get('email')
        User.objects.filter(username=username, is_active=False).delete()
        # ---------------------

        u_form = UserRegisterForm(request.POST)
        p_form = ProfileForm(request.POST, request.FILES)
        
        if u_form.is_valid() and p_form.is_valid():
            try:
                user = u_form.save(commit=False)
                user.is_active = False # Inactive until OTP verified
                user.save()
                
                profile, created = Profile.objects.get_or_create(user=user)
                profile.bio = p_form.cleaned_data.get('bio')
                profile.profile_pic = p_form.cleaned_data.get('profile_pic')
                profile.verification_code = generate_otp()
                profile.save()
                
                send_email(
                    user.email, "Verify Your Account", "Welcome to NoteShare!", 
                    "Please verify your email address to activate your account.", 
                    user.username, profile.verification_code
                )
                
                request.session['verification_id'] = user.id
                
                # === AJAX SUCCESS ===
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'success', 'redirect_url': '/verify/'})
                
                return redirect('verify_email')
            except Exception as e:
                if user.id: user.delete()
                # === AJAX EXCEPTION ===
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'error', 'errors': {'non_field_errors': ["Registration Error. Please try again."]}})
                messages.error(request, "Registration Error. Please try again.")
        else:
            # === AJAX VALIDATION ERRORS ===
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                errors = {}
                # Merge errors from both forms
                for field, error_list in u_form.errors.items():
                    errors[field] = error_list
                for field, error_list in p_form.errors.items():
                    errors[field] = error_list
                return JsonResponse({'status': 'error', 'errors': errors})

    else:
        u_form = UserRegisterForm()
        p_form = ProfileForm()
    return render(request, 'register.html', {'u_form': u_form, 'p_form': p_form})

def verify_email(request):
    if request.method == 'POST':
        code = request.POST.get('code')
        user_id = request.session.get('verification_id')
        if not user_id: 
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': 'Session expired. Login again.'})
            return redirect('login')
        
        try:
            user = User.objects.get(id=user_id)
            if user.profile.verification_code == code:
                user.is_active = True
                user.profile.verification_code = None
                user.save()
                user.profile.save()
                user.backend = 'django.contrib.auth.backends.ModelBackend'
                login(request, user)
                
                send_email(user.email, "Welcome!", "Verification Successful", 
                           "Your account is now active.", user.username)
                
                del request.session['verification_id']
                
                # === AJAX SUCCESS ===
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'success', 'redirect_url': '/'})

                return redirect('home')
            else:
                # === AJAX ERROR ===
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'error', 'message': 'Invalid Verification Code.'})
                messages.error(request, "Invalid Code.")
        except User.DoesNotExist:
            return redirect('register')

    context = {
        'title': 'Activate Account',
        'message': 'Enter the 6-digit code sent to your email to activate your account.',
        'color': 'primary',
        'icon': 'user-check',
        'btn_text': 'Verify & Login'
    }
    return render(request, 'verify_generic.html', context)

# ==========================
# PROFILE SETTINGS & SECURITY
# ==========================

@login_required
def edit_profile(request):
    Profile.objects.get_or_create(user=request.user)
    request.user.refresh_from_db()

    if request.method == 'POST':
        # Security: Password check required for any profile change
        password = request.POST.get('password')
        if not password or not request.user.check_password(password):
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': "Incorrect Password. Changes not saved."})
            messages.error(request, "Incorrect Password. Changes not saved.")
            return redirect('edit_profile')

        try:
            # Update Basic Info
            request.user.first_name = request.POST.get('first_name')
            request.user.last_name = request.POST.get('last_name')
            request.user.profile.bio = request.POST.get('bio')

            request.user.profile.ai_instructions = request.POST.get('ai_instructions')
            # Update Picture
            if request.POST.get('remove_picture') == 'on':
                request.user.profile.profile_pic = None
            elif 'profile_pic' in request.FILES:
                request.user.profile.profile_pic = request.FILES['profile_pic']

            request.user.save()
            request.user.profile.save()

            # Email Change Logic (Step 1)
            new_email = request.POST.get('email')
            if new_email and new_email != request.user.email:
                request.session['pending_email'] = new_email
                otp = generate_otp()
                request.user.profile.verification_code = otp
                request.user.profile.save()
                
                send_email(
                    request.user.email, "Verify Email Change", "Email Change Request", 
                    f"You requested to change email to <b>{new_email}</b>. Verify ownership of CURRENT email.", 
                    request.user.username, otp
                )
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'success', 'redirect_url': '/verify-change/step-1/'})
                return redirect('verify_email_change_old')
            
            # === AJAX SUCCESS (Standard Update) ===
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success', 'message': 'Profile updated successfully!', 'redirect_url': '/profile/'})

            messages.success(request, "Profile updated successfully.")
            return redirect('profile')
            
        except Exception as e:
             if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': "Error updating profile."})
             messages.error(request, "Error updating profile.")

    return render(request, 'edit_profile.html')

@login_required
def verify_email_change_old(request):
    pending_email = request.session.get('pending_email')
    if not pending_email: return redirect('edit_profile')

    if request.method == 'POST':
        code = request.POST.get('code')
        if request.user.profile.verification_code == code:
            # Step 1 Success -> Setup Step 2
            new_otp = generate_otp()
            request.user.profile.verification_code = new_otp
            request.user.profile.save()
            request.session['step1_verified'] = True
            
            send_email(pending_email, "Email Change Step 2", "Verify New Email", 
                       "Confirm ownership of this new email address.", 
                       request.user.username, new_otp)
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success', 'redirect_url': '/verify-change/step-2/'})
            return redirect('verify_email_change_new')
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': "Invalid Code."})
            messages.error(request, "Invalid Code.")

    context = {
        'title': 'Step 1: Verify Old Email',
        'message': f'Enter code sent to CURRENT email: <b>{request.user.email}</b>',
        'color': 'info',
        'icon': 'envelope',
        'btn_text': 'Verify Current Email'
    }
    return render(request, 'verify_generic.html', context)

@login_required
def verify_email_change_new(request):
    pending_email = request.session.get('pending_email')
    if not pending_email or not request.session.get('step1_verified'): 
        return redirect('edit_profile')

    if request.method == 'POST':
        code = request.POST.get('code')
        if request.user.profile.verification_code == code:
            old_email = request.user.email
            
            # Commit Email Change
            request.user.email = pending_email
            request.user.profile.verification_code = None
            request.user.save()
            request.user.profile.save()
            
            # Cleanup
            del request.session['pending_email']
            del request.session['step1_verified']
            
            # Alerts
            send_email(old_email, "Email Changed", "Security Alert", f"Email changed to {pending_email}.", request.user.username)
            send_email(pending_email, "Verified", "Success!", "Email updated successfully.", request.user.username)
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                 return JsonResponse({'status': 'success', 'redirect_url': '/profile/'})
            
            messages.success(request, "Email changed successfully.")
            return redirect('profile')
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': "Invalid Code."})
            messages.error(request, "Invalid Code.")

    context = {
        'title': 'Step 2: Verify New Email',
        'message': f'Enter code sent to NEW email: <b>{pending_email}</b>',
        'color': 'success',
        'icon': 'check-double',
        'btn_text': 'Confirm Change'
    }
    return render(request, 'verify_generic.html', context)

@login_required
def init_delete_account(request):
    if request.method == 'POST':
        otp = generate_otp()
        request.user.profile.verification_code = otp
        request.user.profile.save()
        send_email(request.user.email, "Confirm Deletion", "Account Deletion", 
                   "Enter code to permanently delete your account.", request.user.username, otp)
        
        # AJAX Check
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success', 'redirect_url': '/profile/delete/verify/'})

        return redirect('verify_delete_account')
    return redirect('edit_profile')

@login_required
def verify_delete_account(request):
    if request.method == 'POST':
        if request.user.profile.verification_code == request.POST.get('code'):
            user = request.user
            logout(request)
            user.delete() # Signals in models.py handle file cleanup
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success', 'redirect_url': '/login/'})

            messages.success(request, "Your account has been deleted.")
            return redirect('login')
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': "Invalid Code."})
        messages.error(request, "Invalid Code.")

    context = {
        'title': 'Confirm Deletion',
        'message': 'Enter code to <b class="text-danger">permanently delete</b> your account.',
        'color': 'danger',
        'icon': 'exclamation-triangle',
        'btn_text': 'Permanently Delete'
    }
    return render(request, 'verify_generic.html', context)

# ==========================
# PASSWORD RECOVERY
# ==========================

def forgot_password(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        try:
            user = User.objects.get(username=username)
            if not user.email:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'error', 'message': "No email linked."})
                messages.error(request, "No email linked.")
            else:
                otp = generate_otp()
                user.profile.verification_code = otp
                user.profile.save()
                send_email(user.email, "Reset Password", "Password Reset", "Use this code to reset password.", user.username, otp)
                request.session['reset_user_id'] = user.id
                
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'success', 'redirect_url': '/forgot-password/verify/'})
                
                messages.success(request, f"Code sent to email.")
                return redirect('verify_forgot_code')
        except User.DoesNotExist:
             if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': "Username not found."})
             messages.error(request, "Username not found.")
    return render(request, 'forgot_password.html')

def verify_forgot_code(request):
    user_id = request.session.get('reset_user_id')
    if not user_id: return redirect('forgot_password')
    
    if request.method == 'POST':
        code = request.POST.get('code')
        try:
            user = User.objects.get(id=user_id)
            if user.profile.verification_code == code:
                request.session['code_verified'] = True
                user.profile.verification_code = None
                user.profile.save()
                
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'success', 'redirect_url': '/forgot-password/reset/'})

                return redirect('reset_new_password')
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': "Invalid Code."})
            messages.error(request, "Invalid Code.")
        except User.DoesNotExist:
            return redirect('forgot_password')

    context = {
        'title': 'Reset Password',
        'message': 'Enter code to reset password.',
        'color': 'warning',
        'icon': 'key',
        'btn_text': 'Verify Code'
    }
    return render(request, 'verify_generic.html', context)

def reset_new_password(request):
    if not request.session.get('code_verified'): return redirect('forgot_password')
    
    if request.method == 'POST':
        p1 = request.POST.get('password')
        p2 = request.POST.get('confirm_password')
        if p1 == p2:
            user = User.objects.get(id=request.session['reset_user_id'])
            user.set_password(p1)
            user.save()
            
            # Cleanup
            request.session.pop('reset_user_id', None)
            request.session.pop('code_verified', None)
            
            send_email(user.email, "Security Alert", "Password Changed", "Password reset successful.", user.username)
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success', 'redirect_url': '/login/'})

            messages.success(request, "Password reset successfully. Please login.")
            return redirect('login')
        else:
             if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': "Passwords do not match."})
             messages.error(request, "Passwords do not match.")
    return render(request, 'reset_new_password.html')

def forgot_username(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        users = User.objects.filter(email__iexact=email)
        if users.exists():
            names = ", ".join([u.username for u in users])
            send_email(email, "Your Usernames", "Forgot Username", f"Usernames found: <b>{names}</b>")
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
             return JsonResponse({'status': 'success', 'redirect_url': '/login/'})

        messages.success(request, "If registered, usernames sent to email.")
        return redirect('login')
    return render(request, 'forgot_username.html')

# ==========================
# MAIN APP VIEWS (OPTIMIZED)
# ==========================

@login_required
def home(request):
    query = request.GET.get('q')
    sort_by = request.GET.get('sort', 'recent')
    
    # OPTIMIZATION: Select User+Profile instantly to avoid N+1 queries
    notes = Note.objects.select_related('user', 'user__profile').annotate(
        avg_rating=Avg('ratings__score'), 
        comment_count=Count('comments')
    )

    if query:
        # === WEIGHTED SEARCH ALGORITHM ===
        notes = notes.annotate(
            relevance=(
                Case(When(title__icontains=query, then=Value(10)), default=Value(0), output_field=IntegerField()) +
                Case(When(tags__icontains=query, then=Value(8)), default=Value(0), output_field=IntegerField()) +
                Case(When(course__icontains=query, then=Value(6)), default=Value(0), output_field=IntegerField()) +
                Case(When(user__username__icontains=query, then=Value(4)), default=Value(0), output_field=IntegerField()) +
                Case(When(description__icontains=query, then=Value(2)), default=Value(0), output_field=IntegerField())
            )
        ).filter(relevance__gt=0).order_by('-relevance', '-avg_rating', '-created_at')

    # Sorting overrides
    if sort_by == 'oldest': notes = notes.order_by('created_at')
    elif sort_by == 'most_viewed': notes = notes.order_by('-view_count')
    elif sort_by == 'top_rated': notes = notes.order_by('-avg_rating')
    elif not query: notes = notes.order_by('-created_at')

    # AJAX Capability check (Optional: if frontend handles partial reloads later)
    # Keeping standard return for now as 'search' is not defined as an action-view in logic
    return render(request, 'home.html', {'notes': notes, 'query': query, 'sort_by': sort_by})

@login_required
def profile(request):
    # OPTIMIZED PROFILE VIEW
    notes = Note.objects.filter(user=request.user).select_related('user', 'user__profile').annotate(
        avg_rating=Avg('ratings__score'),
        comment_count=Count('comments')
    ).order_by('-created_at')
    return render(request, 'profile.html', {'notes': notes})

def public_profile(request, username):
    profile_user = get_object_or_404(User, username=username)
    # OPTIMIZED PUBLIC PROFILE
    user_notes = Note.objects.filter(user=profile_user).select_related('user', 'user__profile').annotate(
        avg_rating=Avg('ratings__score'),
        comment_count=Count('comments')
    ).order_by('-created_at')
    return render(request, 'public_profile.html', {'profile_user': profile_user, 'user_notes': user_notes})

@login_required
def note_detail(request, pk):
    note = get_object_or_404(Note, pk=pk)
    
    # View Counting Logic
    session_key = f'viewed_note_{pk}'
    if not request.session.get(session_key, False):
        note.view_count += 1
        note.save()
        request.session[session_key] = True

    avg_rating = round(note.ratings.aggregate(Avg('score'))['score__avg'] or 0, 1)
    
    user_rating = None
    if request.user.is_authenticated:
        rating_obj = note.ratings.filter(user=request.user).first()
        if rating_obj: user_rating = rating_obj.score

    if request.method == 'POST' and 'comment_submit' in request.POST:
        c_form = CommentForm(request.POST)
        if c_form.is_valid():
            new_comment = Comment.objects.create(post=note, user=request.user, text=c_form.cleaned_data['text'])
            
            # --- AJAX HANDLER (Start) ---
            # If the request comes from JavaScript, return JSON instead of reloading
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'success',
                    'username': new_comment.user.username,
                    'text': new_comment.text,
                    'time': 'Just now',
                    'profile_url': f"/user/{new_comment.user.username}/",
                    # Handle Avatar vs Default Initial
                    'avatar_url': new_comment.user.profile.profile_pic.url if new_comment.user.profile.profile_pic else None,
                    'user_initial': new_comment.user.username[0].upper(),
                    'is_author': new_comment.user == note.user,
                    'comment_id': new_comment.pk
                })
            # --- AJAX HANDLER (End) ---

            return redirect('note_detail', pk=pk)
    else:
        c_form = CommentForm()

    comments = note.comments.all().order_by('-created_at')
    return render(request, 'note_detail.html', {'note': note, 'comments': comments, 'c_form': c_form, 'avg_rating': avg_rating, 'user_rating': user_rating})

@login_required
def upload_note(request):
    if request.method == 'POST':
        form = NoteForm(request.POST, request.FILES)
        if form.is_valid():
            note = form.save(commit=False)
            note.user = request.user
            note.save()
            
            # === AJAX SUCCESS ===
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'success', 
                    'message': 'Note uploaded successfully!', 
                    'redirect_url': '/' # Redirect to home or detail
                })

            return redirect('home')
        else:
            # === AJAX ERROR ===
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'errors': form.errors})

    else:
        form = NoteForm()
    return render(request, 'upload_note.html', {'form': form})

@login_required
def edit_note(request, pk):
    note = get_object_or_404(Note, pk=pk)
    # Security check: User must be the owner
    if request.user != note.user: 
        return redirect('home')
    
    if request.method == 'POST':
        form = NoteForm(request.POST, request.FILES, instance=note)
        if form.is_valid():
            form.save()
            
            # === AJAX Response ===
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'success', 
                    'message': 'Changes saved! Redirecting...',
                    'next_url': f"/note/{pk}/"
                })
            # =====================

            messages.success(request, "Note updated successfully.")
            return redirect('note_detail', pk=pk)
        else:
             # === AJAX Form Errors ===
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'errors': form.errors})
    else:
        form = NoteForm(instance=note)
    
    return render(request, 'upload_note.html', {'form': form, 'title': 'Edit Note'})

@login_required
def delete_note(request, pk):
    note = get_object_or_404(Note, pk=pk)
    if request.user == note.user:
        note.delete() # Signals handle file deletion
        
        # === AJAX SUCCESS ===
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success', 'redirect_url': '/profile/'})
            
        messages.success(request, "Note deleted successfully.")
    else:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
             return JsonResponse({'status': 'error', 'message': "Unauthorized"})
        messages.error(request, "Unauthorized")
    return redirect('profile')

@login_required
def rate_note(request, pk):
    if request.method == 'POST':
        note = get_object_or_404(Note, pk=pk)
        score = request.POST.get('score')
        
        # 1. Update/Delete Logic
        if score == '0':
            Rating.objects.filter(user=request.user, note=note).delete()
            user_score = 0
        elif score: 
            Rating.objects.update_or_create(user=request.user, note=note, defaults={'score': int(score)})
            user_score = int(score)
            
        # 2. AJAX Response (No Reload)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            # Calculate new average
            new_avg = note.ratings.aggregate(Avg('score'))['score__avg'] or 0
            new_avg = round(new_avg, 1)
            
            return JsonResponse({
                'status': 'success',
                'avg_rating': new_avg,
                'user_score': user_score,
                'count': note.ratings.count()
            })

    return redirect('note_detail', pk=pk)

@login_required
def delete_comment(request, pk):
    comment = get_object_or_404(Comment, pk=pk)
    
    # Security check
    if request.user == comment.user or request.user == comment.post.user:
        if request.method == 'POST':
            comment.delete()
            
            # AJAX Response
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success', 'pk': pk})
            
            # Standard Fallback
            return redirect('note_detail', pk=comment.post.pk)
            
    return redirect('home')

# ==========================
# AI CHAT FEATURES (NEW)
# ==========================

@login_required
def ai_chat_page(request, pk):
    """ 
    Renders the Split-Screen Study Mode with Pre-calculated AI Diagnostics.
    """
    note = get_object_or_404(Note, pk=pk)
    
    # === AI CONTEXT DIAGNOSTIC SYSTEM ===
    # Determines if the file is suitable for direct AI processing or fallback mode.
    
    ai_status = 'ready' # Default: Full capability
    status_msg = "Full File Context Active"
    
    # Configuration
    MAX_SIZE_BYTES = 200 * 1024 * 1024 # 200MB Limit

    if not note.file:
        ai_status = 'no_file'
        status_msg = "Metadata Only (No File)"
    else:
        try:
            # 1. PHYSICAL CHECK
            if not os.path.exists(note.file.path):
                ai_status = 'error'
                status_msg = "Server Error: File Missing"
            
            # 2. SIZE CHECK
            elif note.file.size > MAX_SIZE_BYTES:
                ai_status = 'too_large'
                mb_size = note.file.size / (1024*1024)
                status_msg = f"File Too Large ({mb_size:.0f}MB) • Metadata Mode"
            
            else:
                # 3. TYPE CHECK
                raw_path = note.file.path
                ext = raw_path.split('.')[-1].lower()
                
                # List of types Gemini 1.5/2.0 accepts via Files API
                supported_exts = [
                    'pdf', 'txt', 'md', 'csv', 'html', 'htm', 'xml', 'json', 'yaml', 'yml', 
                    'py', 'js', 'java', 'c', 'cpp', 'h', 'css', 'sql', 'sh', 'bat', 'php'
                ]
                
                # Check media types
                guessed_type, _ = mimetypes.guess_type(raw_path)
                is_media = guessed_type and guessed_type.startswith(('image/', 'video/', 'audio/'))

                if ext not in supported_exts and not is_media:
                    # e.g. .xlsx, .docx, .zip
                    ai_status = 'unsupported'
                    status_msg = f"Unsupported Format ({ext.upper()}) • Metadata Mode"
                    
        except Exception as e:
            ai_status = 'error'
            status_msg = "File Access Error • Metadata Mode"

    context = {
        'note': note,
        'ai_status': ai_status,   # Used for badge color logic
        'status_msg': status_msg  # Used for text display
    }
    return render(request, 'ai_chat.html', context)

@login_required
def ai_chat_api(request):
    if request.method == 'POST':
        try:
            # 1. Parse Data
            data = json.loads(request.body)
            user_message = data.get('message', '')
            note_id = data.get('note_id')
            use_file = data.get('use_file', False)  # The green button toggle

            if not user_message:
                return JsonResponse({'error': "Message empty."}, status=400)

            # 2. Get Note Object
            note = get_object_or_404(Note, pk=note_id)
            
            # 3. Build Text Context (Metadata + Comments)
            uploaded_dt = note.created_at.strftime("%B %d, %Y")
            
            # Get last 10 comments for context
            latest_comments = note.comments.select_related('user').order_by('-created_at')[:10]
            comment_str = ""
            if latest_comments:
                for c in reversed(latest_comments):
                    comment_str += f"- {c.user.username}: {c.text}\n"
            else:
                comment_str = "No comments yet."

            context_text = (
                f"=== NOTE METADATA ===\n"
                f"Title: {note.title}\n"
                f"Description: {note.description}\n"
                f"Course: {note.course}\n"
                f"Tags: {note.tags}\n"
                f"Uploaded By: {note.user.username}\n"
                f"Date: {uploaded_dt}\n\n"
                f"=== COMMUNITY COMMENTS ===\n{comment_str}"
            )

            # 4. ROBUST FILE HANDLING
            file_path = None
            mime_type = None
            
            # Safe Limit: 200MB (prevent server timeouts)
            MAX_SIZE_BYTES = 200 * 1024 * 1024 

            # Only process file if User toggled it ON AND file exists
            if use_file and note.file:
                try:
                    real_path = note.file.path
                    
                    # A. Physical Check
                    if not os.path.exists(real_path):
                        context_text += "\n\n[SYSTEM WARNING: File not found on server disk. Answer based on metadata.]"
                    
                    # B. Size Check
                    elif note.file.size > MAX_SIZE_BYTES:
                        size_mb = note.file.size / (1024 * 1024)
                        context_text += f"\n\n[SYSTEM NOTE: File skipped because it is too large ({size_mb:.1f} MB). Limit is 200 MB.]"
                    
                    # C. MIME Type & Logic
                    else:
                        mimetypes.init()
                        ext = real_path.split('.')[-1].lower()
                        
                        # -- TYPE 1: Native PDF --
                        if ext == 'pdf':
                            mime_type = 'application/pdf'
                            file_path = real_path

                        # -- TYPE 2: Code/Text (Force Text) --
                        elif ext in ['txt', 'md', 'csv', 'html', 'xml', 'json', 'yaml', 'env', 
                                     'py', 'js', 'java', 'c', 'cpp', 'css', 'sql', 'php', 'rb', 'go', 'ts']:
                            mime_type = 'text/plain'
                            file_path = real_path

                        # -- TYPE 3: Media (Image/Audio/Video) --
                        else:
                            guessed_type, _ = mimetypes.guess_type(real_path)
                            if guessed_type and guessed_type.startswith(('image/', 'video/', 'audio/')):
                                mime_type = guessed_type
                                file_path = real_path
                            else:
                                # Unsupported (e.g., .xlsx, .docx, .zip) -> Fallback to Context
                                context_text += f"\n\n[SYSTEM NOTE: The file type ({ext}) cannot be read directly by AI. Answer based on Metadata & Comments.]"

                except Exception as e:
                    print(f"File Check Error: {e}")
                    context_text += f"\n[System Error reading file: {str(e)}]"
                    file_path = None

            # 5. Call Gemini Wrapper
            # (Assuming you don't have user_instructions yet, passing empty string)
            ai_response = generate_study_help(
                user_prompt=user_message,
                context=context_text,
                user_instructions="", 
                file_path=file_path,
                mime_type=mime_type
            )

            return JsonResponse({'response': ai_response})

        except Exception as e:
            print(f"API Error: {e}")
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'POST only'}, status=405)

# ==========================
# MEDIA SERVING (FORCE INLINE)
# ==========================

def serve_media_inline(request, path):
    """
    Custom view to serve media files with 'Content-Disposition: inline'.
    This forces the browser to open PDFs/Images/Videos instead of downloading them.
    """
    # Construct full path
    file_path = os.path.join(settings.MEDIA_ROOT, path)

    # Security check: Prevent directory traversal (e.g. ../../settings.py)
    if not os.path.normpath(file_path).startswith(os.path.normpath(settings.MEDIA_ROOT)):
        raise Http404("Access Denied")

    if not os.path.exists(file_path):
        raise Http404("File not found")

    # Guess the MIME type (e.g. 'application/pdf', 'video/mp4')
    content_type, encoding = mimetypes.guess_type(file_path)
    content_type = content_type or 'application/octet-stream'

    # Open the file
    response = FileResponse(open(file_path, 'rb'), content_type=content_type)

    # MAGIC HEADER: 'inline' tells browser to render it. 
    # 'attachment' would force download.
    response['Content-Disposition'] = f'inline; filename="{os.path.basename(file_path)}"'

    return response