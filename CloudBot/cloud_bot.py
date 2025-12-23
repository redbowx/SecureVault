import os
import time
import threading
import telebot
import pyrebase
from flask import Flask

# --- FLASK UYGULAMASI ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Calisiyor! 🚀", 200

# --- YAPILANDIRMA ---
# Render/Heroku Environment Variables
FIREBASE_CONFIG = {
    "apiKey": os.environ.get("FIREBASE_API_KEY"),
    "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN"),
    "databaseURL": os.environ.get("FIREBASE_DB_URL"),
    "storageBucket": os.environ.get("FIREBASE_STORAGE_BUCKET"),
}

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
BOT_EMAIL = os.environ.get("BOT_EMAIL")
BOT_PASSWORD = os.environ.get("BOT_PASSWORD")

# Global Değişkenler
bot = None
db = None
auth = None

# --- BOT MANTIĞI ---
def start_bot_logic():
    global bot, db, auth
    print("Bot mantığı başlatılıyor...")

    # 1. Kontroller
    if not BOT_TOKEN or not CHAT_ID:
        print("HATA: Telegram Token veya Chat ID eksik.")
        return

    # 2. Başlatma
    try:
        bot = telebot.TeleBot(BOT_TOKEN)
        firebase = pyrebase.initialize_app(FIREBASE_CONFIG)
        auth = firebase.auth()
        db = firebase.database()
    except Exception as e:
        print(f"Başlatma Hatası: {e}")
        return

    # 3. Stream Handler
    def stream_handler(message):
        try:
            # Sadece yeni veri ekleme (put/patch) ve data doluysa
            if message['event'] in ('put', 'patch') and message['data'] is not None:
                # İlk yükleme (path='/') değilse
                if message['path'] != '/':
                    new_data = message['data']
                    if isinstance(new_data, dict):
                        send_telegram_alert(new_data)
        except Exception as e:
            print(f"Stream Hatası: {e}")

    # 4. Telegram Gönderimi
    def send_telegram_alert(data):
        try:
            timestamp = data.get('timestamp', '-')
            email = data.get('email', 'Bilinmiyor')
            username = data.get('username', 'Bilinmiyor')
            
            msg = (
                f"🚨 <b>YENİ ŞİFRE SIFIRLAMA TALEBİ</b>\n\n"
                f"👤 <b>Kullanıcı:</b> {username}\n"
                f"📧 <b>Email:</b> {email}\n"
                f"⏰ <b>Zaman:</b> {timestamp}\n\n"
                f"<i>Admin Paneline gidip onaylayın.</i>"
            )
            bot.send_message(CHAT_ID, msg, parse_mode='HTML')
            print(f"Bildirim gönderildi: {email}")
        except Exception as e:
            print(f"Telegram Hatası: {e}")

    # 5. Ana Döngü (Login + Listen)
    while True:
        try:
            print(f"Giriş yapılıyor: {BOT_EMAIL}...")
            user = auth.sign_in_with_email_and_password(BOT_EMAIL, BOT_PASSWORD)
            id_token = user['idToken']
            print("Giriş Başarılı. Dinleme başlıyor...")

            # Stream başlat
            stream = db.child("reset_requests").stream(stream_handler, token=id_token)
            
            # Stream'in kopmaması için sonsuz döngü (Token yenileme gerekebilir)
            # Pyrebase stream thread'i ayrı çalışır, biz ana thread'i burada tutuyoruz.
            # Basitlik için her 50 dakikada bir yeniden başlatalım (Token ömrü genelde 1 saat)
            time.sleep(3000) 
            
            print("Token yenilemek için stream yeniden başlatılıyor...")
            stream.close() 
            
        except Exception as e:
            print(f"Bağlantı Hatası: {e}")
            print("10 saniye sonra tekrar denenecek...")
            time.sleep(10)

# --- ANA ÇALIŞTIRMA ---
if __name__ == "__main__":
    # 1. Botu Arka Planda Başlat
    bot_thread = threading.Thread(target=start_bot_logic, daemon=True)
    bot_thread.start()
    
    # 2. Flask Sunucusunu Başlat (Render Portu Dinleyecek)
    port = int(os.environ.get("PORT", 5000))
    print(f"Web Sunucusu {port} portunda başlatılıyor...")
    app.run(host='0.0.0.0', port=port)
