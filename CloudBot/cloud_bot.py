import os
import time
import json
import telebot
import pyrebase
from datetime import datetime

# Try to load local .env file (for local testing only)
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("Local .env file loaded.")
except ImportError:
    print("python-dotenv not found, relying on system environment variables.")

# --- CONFIGURATION ---
# These values must be set in your Render/Heroku Environment Variables
FIREBASE_CONFIG = {
    "apiKey": os.environ.get("FIREBASE_API_KEY"),
    "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN"),
    "databaseURL": os.environ.get("FIREBASE_DB_URL"),
    "storageBucket": os.environ.get("FIREBASE_STORAGE_BUCKET"),
}

# Bot Credentials
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Account to authenticate the Listener (Must have read access to 'reset_requests')
BOT_EMAIL = os.environ.get("BOT_EMAIL")
BOT_PASSWORD = os.environ.get("BOT_PASSWORD")

# --- INITIALIZATION ---
if not BOT_TOKEN or not CHAT_ID:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID env vars.")

bot = telebot.TeleBot(BOT_TOKEN)
firebase = pyrebase.initialize_app(FIREBASE_CONFIG)
auth = firebase.auth()
db = firebase.database()

def send_telegram_alert(data):
    """Formats and sends the alert message."""
    try:
        timestamp = data.get('timestamp', 'Unknown Time')
        email = data.get('email', 'Unknown Email')
        username = data.get('username', 'Unknown User')
        
        # Convert timestamp to readable format if it's a standard format
        # Assuming simple string for now, but you can parse it if needed.

        message_text = (
            f"🚨 <b>NEW PASSWORD RESET REQUEST</b> 🚨\n\n"
            f"👤 <b>User:</b> {username}\n"
            f"📧 <b>Email:</b> {email}\n"
            f"⏰ <b>Time:</b> {timestamp}\n\n"
            f"<i>Please check the Admin Panel to approve or deny.</i>"
        )
        
        bot.send_message(CHAT_ID, message_text, parse_mode='HTML')
        print(f"Alert sent for {email}")
        
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def stream_handler(message):
    """Callback function for Firebase Stream."""
    try:
        # message['event'] can be 'put', 'patch', etc.
        # message['path'] is the relative path
        # message['data'] is the new data
        
        print(f"Event: {message['event']}, Path: {message['path']}")

        # We only care about new data (put) that is not None (deletion)
        if message['event'] in ('put', 'patch') and message['data'] is not None:
            
            # If the update is the root object (initial load or mass update)
            if message['path'] == '/':
                # If it's a dict of requests, iterate them (careful with initial load)
                if isinstance(message['data'], dict):
                    for key, val in message['data'].items():
                        # Optional: Add logic here to avoid spamming on startup
                        # For now, we assume this runs continuously and catches new ones.
                        pass
            else:
                # A specific child was added/updated
                new_data = message['data']
                # Ensure it's a dictionary (actual request data)
                if isinstance(new_data, dict):
                    send_telegram_alert(new_data)
                    
    except Exception as e:
        print(f"Error in stream handler: {e}")

def main():
    print("Starting Cloud Bot...")
    
    # 1. Authenticate
    try:
        print(f"Authenticating as {BOT_EMAIL}...")
        user = auth.sign_in_with_email_and_password(BOT_EMAIL, BOT_PASSWORD)
        id_token = user['idToken']
        print("Authentication successful.")
    except Exception as e:
        print(f"Authentication failed: {e}")
        return

    # 2. Start Stream Loop
    while True:
        try:
            print("Listening to 'reset_requests'...")
            # stream() returns a closable stream object, but we block here for simplicity in this script structure
            # or we keep the script alive. Pyrebase stream runs in a thread.
            stream = db.child("reset_requests").stream(stream_handler, token=id_token)
            
            # Keep the main thread alive to let the stream thread run
            while True:
                time.sleep(60)
                # Optional: Refresh token logic could go here if needed for long runs
                # But Pyrebase stream usually handles simple connection drops.
                
        except KeyboardInterrupt:
            print("Stopping bot...")
            if 'stream' in locals():
                stream.close()
            break
        except Exception as e:
            print(f"Stream connection lost: {e}")
            print("Reconnecting in 10 seconds...")
            time.sleep(10)
            # Re-auth might be needed if token expired
            try:
                user = auth.sign_in_with_email_and_password(BOT_EMAIL, BOT_PASSWORD)
                id_token = user['idToken']
            except:
                pass

if __name__ == "__main__":
    main()
