# VanityTweaks Server

Bu klasör VanityTweaks'in web sunucusunu içerir.

## Render'a Deploy

### Adım 1: GitHub'a yükle
1. [github.com](https://github.com) → yeni repo oluştur (örn: `vanitytweaks-server`)
2. Bu `server/` klasörünü repo'nun kök dizinine at
3. Push et

### Adım 2: Render'a bağla
1. [render.com](https://render.com) → ücretsiz hesap aç (GitHub ile giriş)
2. Dashboard → **New +** → **Web Service**
3. GitHub repo'nu bağla
4. Ayarlar:
   - **Name**: `vanitytweaks`
   - **Runtime**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT`
5. **Create Web Service** tıkla

### Adım 3: Hazır!
- Siteniz: `https://vanitytweaks.onrender.com`
- Admin: `https://vanitytweaks.onrender.com/admin`
- Giriş: `admin` / `admin123` (ilk girişte değiştirin!)

## Dosyalar
- `app.py` — Ana Flask uygulaması
- `models.py` — Veritabanı modelleri
- `Procfile` — Render başlatma komutu
- `render.yaml` — Render yapılandırması
- `requirements.txt` — Python bağımlılıkları
- `templates/` — HTML sayfaları
- `static/` — CSS dosyaları
