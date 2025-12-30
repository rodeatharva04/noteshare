import os
import threading
from django.conf import settings
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
import random

def delete_file_if_exists(file_field):
    if file_field and file_field.name:
        if os.path.isfile(file_field.path):
            try:
                os.remove(file_field.path)
                print(f"✅ File Deleted: {file_field.path}")
            except Exception as e:
                print(f"❌ Error deleting file: {e}")

def get_email_html(title, body_content, code=None, footer_text="Happy Learning!"):
    header_color = "#667eea"
    if "Alert" in title or "Delete" in title:
        header_color = "#d93025"
    elif "Welcome" in title:
        header_color = "#0f9d58"

    code_block = ""
    if code:
        code_block = f"""
        <div style="background-color: #f8f9fa; border: 2px dashed {header_color}; color: #333; 
                    font-size: 24px; font-weight: bold; padding: 15px; display: inline-block; 
                    margin: 20px 0; letter-spacing: 5px; border-radius: 8px;">
            {code}
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f4; margin: 0; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
            <div style="background: {header_color}; padding: 30px; text-align: center; color: white;">
                <h1 style="margin: 0; font-size: 24px;">NoteShare</h1>
                <p style="margin: 5px 0 0; opacity: 0.9;">{title}</p>
            </div>
            <div style="padding: 40px; text-align: center; color: #333;">
                <p style="font-size: 16px; line-height: 1.5;">{body_content}</p>
                {code_block}
                <div style="margin-top: 20px; font-size: 12px; color: #999;">
                    Time: {settings.TIME_ZONE} | System Generated
                </div>
            </div>
            <div style="background-color: #f8f9fa; padding: 15px; text-align: center; font-size: 12px; color: #888;">
                &copy; 2025 NoteShare. {footer_text}
            </div>
        </div>
    </body>
    </html>
    """
    return html

def _send_brevo_task(to_email, subject, html_content, name):
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = settings.BREVO_API_KEY
    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
    
    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": to_email, "name": name}],
        sender={"email": settings.DEFAULT_FROM_EMAIL, "name": "NoteShare Security"},
        subject=subject,
        html_content=html_content
    )
    try:
        api_instance.send_transac_email(send_smtp_email)
    except ApiException as e:
        print(f"❌ Email Failed: {e}")

def send_email(to_email, subject, title, body, user_name="User", code=None):
    html_content = get_email_html(title, body, code)
    
    email_thread = threading.Thread(
        target=_send_brevo_task, 
        args=(to_email, subject, html_content, user_name)
    )
    email_thread.start()

def generate_otp():
    return str(random.randint(100000, 999999))
