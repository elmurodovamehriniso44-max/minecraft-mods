# Minecraft Bedrock katalog boti (aiogram 3)

Modlar, kartalar, teksturalar, skinlar va shaderlar katalogi + qidiruv + admin panel.

## Fayllar
- `main.py` — ishga tushirish (Renderda webhook, lokalda polling)
- `config.py`, `texts.py`, `keyboards.py`
- `db.py` — SQLAlchemy (SQLite yoki PostgreSQL)
- `handlers_user.py`, `handlers_admin.py`
- `requirements.txt`, `render.yaml`, `.env.example`, `.gitignore`

## Lokal ishga tushirish
```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env     # BOT_TOKEN va ADMIN_IDS ni to'ldiring
python main.py
```

## GitHub + Render
1. Loyihani GitHub repozitoriyga yuklang (`.env` yuklanmaydi — `.gitignore`da bor).
2. **Bepul PostgreSQL oching** (Neon.tech yoki Supabase) va ulanish manzilini oling.
   ⚠️ Render bepul tarifida disk vaqtinchalik — SQLite ma'lumotlari har restartda o'chadi.
3. Render → **New → Blueprint** → repozitoriyni tanlang (`render.yaml` avtomatik o'qiladi)
   yoki **New → Web Service** (Build: `pip install -r requirements.txt`, Start: `python main.py`).
4. Environment o'zgaruvchilari: `BOT_TOKEN`, `ADMIN_IDS`, `DATABASE_URL`.
5. Deploy tugagach bot webhook orqali avtomatik ishlaydi (`RENDER_EXTERNAL_URL` ni Render o'zi beradi).
6. Bepul tarifda servis 15 daqiqa so'rovsiz qolsa uxlaydi. [UptimeRobot](https://uptimerobot.com)
   orqali `https://<servis>.onrender.com/health` manzilini har 5 daqiqada ping qiling.

## Foydalanish
- Admin: `/admin` → qo'shish / tahrirlash / o'chirish / rassilka / statistika
- Fayllar Telegram serverida `file_id` orqali saqlanadi — alohida storage kerak emas.
- Faylni admin panelda **hujjat (File)** sifatida yuboring.
