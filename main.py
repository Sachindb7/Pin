import os
import time
import json
import re
from datetime import datetime
import gspread 
from oauth2client.service_account import ServiceAccountCredentials 
from dotenv import load_dotenv
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

# 1. SETUP
load_dotenv()
BLOG_ID = os.getenv('BLOG_ID')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# --- GOOGLE SHEETS LOGGING ---
def log_to_gsheet(title, post_url, tags, desc, img_url, aff_link):
    try:
        creds_json = os.getenv('G_SHEET_CREDS')
        if not creds_json:
            print("⚠️ Sheet Creds not found! Skipping logging.")
            return

        creds_dict = json.loads(creds_json)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # Open specific sheet - ensure this name matches your Google Sheet
        sheet = client.open("CricHub_Logs").sheet1 
        
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Order: Date | Title | Post URL | Affiliate Link | Image URL | Description | Tags
        sheet.append_row([date_str, title, post_url, aff_link, img_url, desc, tags])
        print("📊 Data Logged to Google Sheet Successfully!")
        
    except Exception as e:
        print(f"⚠️ Google Sheet Error: {e}")
# -------------------------------------------

# --- AUTH LOGIC ---
SCOPES = ['https://www.googleapis.com/auth/blogger']
creds = None

# 1. Try to load from local file first (Persisted session)
if os.path.exists('token.json'):
    try:
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    except Exception:
        print("⚠️ Corrupt token.json, deleting...")
        os.remove('token.json')

# 2. Check validity
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            print("⚠️ Token expired/invalid. Re-authenticating...")
            creds = None

    # 3. If no valid file, try Env Vars (Legacy/CI method) but handle failure
    if not creds and os.getenv('REFRESH_TOKEN'):
        print("🔄 Attempting auth via Environment Variables...")
        try:
            temp_creds = Credentials(
                None,
                refresh_token=os.getenv('REFRESH_TOKEN'),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.getenv('CLIENT_ID'),
                client_secret=os.getenv('CLIENT_SECRET'),
                scopes=SCOPES
            )
            temp_creds.refresh(Request())
            creds = temp_creds
        except Exception as e:
            print(f"⚠️ Env Var Auth Failed (Invalid Grant/Token): {e}")
            creds = None

    # 4. Fallback: Browser Login (Interactive)
    if not creds:
        print("🌍 Initiating Browser Login... Please check your browser.")
        if not os.getenv('CLIENT_ID') or not os.getenv('CLIENT_SECRET'):
            print("❌ ERROR: CLIENT_ID and CLIENT_SECRET must be set in .env")
            exit()
            
        client_config = {
            "installed": {
                "client_id": os.getenv('CLIENT_ID'),
                "client_secret": os.getenv('CLIENT_SECRET'),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"]
            }
        }
        try:
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=0)
        except Exception as e:
            print(f"❌ Browser Authentication Failed: {e}")
            exit()
            
    # Save the new credentials for next run
    with open('token.json', 'w') as token:
        token.write(creds.to_json())

blogger_service = build('blogger', 'v3', credentials=creds)
# ------------------

# 2. READ DATA ROW
try:
    with open('topics.txt', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    if not lines: 
        print("No data rows left!")
        exit()
    raw_row = lines[0].strip()
    remaining_rows = lines[1:]
except FileNotFoundError:
    print("topics.txt file not found!")
    exit()

print(f"🔄 Processing Row: {raw_row[:50]}...")

parts = raw_row.split('\t')

def get_part(index):
    return parts[index].strip() if len(parts) > index else ""

# --- HELPER TO FIX DRIVE IMAGES ---
def fix_drive_image_url(url):
    # Extracts ID from standard drive links and converts to direct content link
    # Matches id=XXXX or /d/XXXX
    match = re.search(r'(?:id=|\/d\/)([\w-]+)', url)
    if match:
        file_id = match.group(1)
        # using lh3.googleusercontent.com/d/ID usually bypasses download warnings for images
        return f"https://lh3.googleusercontent.com/d/{file_id}"
    return url
# ----------------------------------

data_title = get_part(0)
raw_image = get_part(1)
data_image = fix_drive_image_url(raw_image) # Apply fix immediately
data_board = get_part(2)
data_desc = get_part(4)
data_link = get_part(5)
data_date = get_part(6)
data_tags = get_part(7)

if not data_title:
    print("❌ Error: Title missing in row. Skipping.")
    exit()

print(f"✨ Generating Fashion Blog for: {data_title}")
print(f"🖼️  Image fixed: {data_image}")

client = genai.Client(api_key=GEMINI_API_KEY)

# 3. PROMPT
prompt_text = f"""
You are an expert fashion and lifestyle blogger known for SEO-optimized, engaging, and aesthetically pleasing content.

I need you to generate a full HTML blog post body based on the following details. 
The output must be raw HTML suitable for pasting directly into the "HTML View" of Blogger (Blogspot).

**Input Details:**
- **Title:** {data_title}
- **Image URL:** {data_image}
- **Category/Board:** {data_board}
- **Description:** {data_desc}
- **Product Link:** {data_link}
- **Keywords:** {data_tags}

**Requirements:**
1.  **Structure:** 
    - Start with an engaging introduction.
    - Embed the main image: <div style="text-align: center; margin: 20px 0;"><img src="{data_image}" alt="{data_title}" style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"></div>
    - Break down the "Look" or "Topic" into bullet points or short paragraphs.
    - Explain *why* this works (styling tips, usage, etc.).
    - Include a clear "Shop This Look" Call-to-Action (CTA) button or bold link using the Product Link: {data_link}
    - End with a conclusion and a question to encourage comments.
2.  **Formatting:**
    - Use clean HTML tags: <h2>, <p>, <ul>, <li>, <b>, <i>, <br>.
    - Add inline CSS styles to the "Shop" button (e.g., background-color: #bd081c; color: white; padding: 12px 24px; text-decoration: none; border-radius: 24px; font-weight: bold; display: inline-block; margin-top: 10px;).
    - Tone: Personal, friendly, and helpful.
3.  **SEO:**
    - Naturally weave the provided Keywords into the text.

**Output:**
Return ONLY the HTML code string. Do not wrap it in markdown code blocks. Do not include <html>, <head>, or <body> tags.
"""

# Generating
try:
    response = client.models.generate_content(
        model="gemini-3-flash-preview", 
        contents=prompt_text
    )
    
    # 4. CLEANING
    content_html = response.text.replace("```html", "").replace("```", "").strip()

    final_labels = [tag.strip() for tag in data_tags.split(',')] if data_tags else []
    final_labels = [l for l in final_labels if l]
    if data_board:
        final_labels.append(data_board)
    final_labels.append("Fashion")

    seo_desc = f"{data_title}: {data_desc}"
    if len(seo_desc) > 150:
        seo_desc = seo_desc[:147] + "..."

    # 5. UPLOAD
    body = {
        "kind": "blogger#post",
        "blog": {"id": BLOG_ID},
        "title": data_title, 
        "content": content_html,
        "labels": final_labels
    }

    posts = blogger_service.posts()
    draft_result = posts.insert(blogId=BLOG_ID, body=body, isDraft=False).execute()
    post_id = draft_result['id']
    post_url = draft_result['url']
    print(f"✅ Post Created! ID: {post_id}")
    print(f"📝 Title: {data_title}")
    
    time.sleep(2)

    patch_body = { "searchDescription": seo_desc }
    posts.patch(blogId=BLOG_ID, postId=post_id, body=patch_body).execute()
    print(f"✅ SEO Description Added.")
    print(f"🚀 Final Link: {post_url}")

    # Pass all new fields to the logger
    log_to_gsheet(data_title, post_url, data_tags, data_desc, data_image, data_link)
    
    with open('topics.txt', 'w', encoding='utf-8') as f:
        f.writelines(remaining_rows)

except Exception as e:
    print(f"❌ Error: {e}")
