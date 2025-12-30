import google.generativeai as genai
from django.conf import settings
import logging
import time

logger = logging.getLogger(__name__)

def generate_study_help(user_prompt: str, context: str = "", user_instructions: str = None, file_path: str = None, mime_type: str = None) -> str:
    # 1. Configure API
    api_key = getattr(settings, 'GOOGLE_API_KEY', None)
    if not api_key:
        return "Configuration Error: Google API Key not found."

    genai.configure(api_key=api_key)

    try:
        # 2. Select Model (Using 2.5 Flash for superior speed/stability in AJAX calls)
        model = genai.GenerativeModel('gemini-2.5-flash') 
        
        # 3. Prepare System Instructions
        base_instruction = (
            "You are a helpful student assistant. "
            "Use Markdown for text formatting. "
            "For Math, use LaTeX wrapped in $ or $$. "
            "CRITICAL: Wrap commands like \\left in backticks if explaining them. "
        )

        if user_instructions and user_instructions.strip():
            base_instruction += f"\n\nUSER PREFERENCES:\n{user_instructions}\n"

        # 4. Handle File Upload
        uploaded_file = None
        content_parts = [base_instruction]

        if file_path and mime_type:
            try:
                # Upload to Gemini
                uploaded_file = genai.upload_file(file_path, mime_type=mime_type)
                
                # --- ROBUST WAIT LOOP ---
                # Wait maximum 30 seconds for processing (Video/PDF)
                # This prevents the AJAX call from failing if Google is slow
                max_retries = 30
                retry_count = 0
                
                while uploaded_file.state.name == "PROCESSING":
                    if retry_count > max_retries:
                        raise TimeoutError("File processing timed out.")
                    time.sleep(1)
                    uploaded_file = genai.get_file(uploaded_file.name)
                    retry_count += 1

                if uploaded_file.state.name == "FAILED":
                    raise ValueError("Google AI failed to process this file.")
                
                content_parts.append(uploaded_file)
                content_parts.append("(File content is attached above)")
                
            except Exception as e:
                logger.error(f"File Upload Error: {e}")
                # Don't crash entire chat if file fails; just send text
                content_parts.append(f"\n[System Warning: Could not analyze the file directly ({str(e)}). Using metadata only.]")

        # 5. Add Context & Question
        if context:
            content_parts.append(f"\n\n=== METADATA & COMMENTS ===\n{context}")
        
        content_parts.append(f"\n\n=== USER QUESTION ===\n{user_prompt}")

        # 6. Generate Response
        response = model.generate_content(content_parts)
        
        # 7. Cleanup (Delete file from Google Cloud)
        if uploaded_file:
            try:
                uploaded_file.delete()
            except:
                pass 

        return response.text

    except Exception as e:
        logger.error(f"Gemini Logic Error: {e}")
        return f"AI Error: {str(e)}"