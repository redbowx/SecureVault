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

import collections

# Global Değişkenler
bot = None
db = None
auth = None
# Tekrar bildirimlerini önlemek için son 50 ID'yi tutan kuyruk
processed_ids = collections.deque(maxlen=50)

# --- BOT MANTIĞI ---
def start_bot_logic():
    global bot, db, auth, processed_ids
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
            event = message.get("event")
            path = message.get("path")
            data = message.get("data")

            # Sadece yeni veri ekleme (put) olaylarını işle
            if event != "put" or data is None:
                return

            requests_to_process = {}

            # DURUM A: Tek bir veri geldiyse (Path: /push_id)
            if path != "/":
                request_id = path.replace("/", "")
                requests_to_process[request_id] = data
            
            # DURUM B: Kök dizin geldiyse (Path: /)
            elif isinstance(data, dict):
                # Başlangıçta tüm listeyi işlememek için sadece yeni eklenenleri bulmak zordur.
                # Ancak duplicate check sayesinde eski mesajları tekrar atmayacağız.
                requests_to_process = data

            # İşlenecek Talepleri Filtrele ve Gönder
            for req_id, req_data in requests_to_process.items():
                if not isinstance(req_data, dict): continue
                
                # --- DUPLICATE CHECK ---
                if req_id in processed_ids:
                    # Zaten işledik, atla
                    continue
                
                # Sadece 'pending' talepleri
                if req_data.get('status') == 'pending':
                    send_telegram_alert(req_data)
                    # ID'yi kaydet (Otomatik olarak en eski silinir 50'yi geçince)
                    processed_ids.append(req_id)
                    print(f"İşlendi: {req_id}")

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
