# 🎵 Link → Shazam → MP3 Telegram bot (aiogram 3)

Havola (Instagram Reels, TikTok, YouTube Shorts, oddiy video) yuboriladi → audio `workdir` ga tortiladi →
`shazamio` qo'shiqni aniqlaydi → YouTube (zaxira: SoundCloud) dan to'liq MP3 yuklanadi →
`mutagen` teg + muqova yozadi → `file_id` SQLite'ga keshlanadi.

## Struktura
```
main.py            kirish nuqtasi (polling + Render health-server)
config.py          token, yo'llar, limitlar, cookies/player_client sozlamalari
middlewares.py     foydalanuvchini yozish + majburiy obuna (sub-check)
handlers/          start.py, music.py, inline.py, admin.py
services/          downloader.py, recognizer.py, tagger.py, db.py, utils.py
Dockerfile         ffmpeg + deno + Python (Render uchun)
render.yaml        Render Blueprint
```
Papka va fayl nomlari **faqat kichik harfda** (Linux katta-kichik harfni farqlaydi).

## Lokal ishga tushirish
1. `ffmpeg` o'rnating (`sudo apt install ffmpeg`)
2. `pip install -r requirements.txt`
3. `.env.example` → `.env`, to'ldiring
4. `python main.py`

BotFather: `/setinline` bilan inline rejimni yoqing; botni majburiy obuna kanaliga **admin** qiling.

## Render.com (24/7)

### 1) FFmpeg — Aptfile ISHLAMAYDI
`Aptfile` Heroku buildpack'i uchun; **Render'da u e'tiborga olinmaydi**, Render'ning oddiy Python
muhitida esa `apt install` qilib bo'lmaydi. Shuning uchun **Dockerfile** ishlatiladi (ichida `ffmpeg`
va `deno` — yt-dlp YouTube uchun JS runtime sifatida ishlatadi). Render'da: New → Web Service →
**Runtime: Docker**.

### 2) Muhit o'zgaruvchilari
`BOT_TOKEN`, `ADMIN_IDS`, `CHANNEL_ID`, `CHANNEL_URL`. Free tarifda `MAX_PARALLEL_JOBS=1` (512 MB RAM).

### 3) YouTube IP blokirovkasi — cookies.txt
- Render → Service → **Environment → Secret Files** → fayl nomi `cookies.txt`, ichiga cookie matnini joylang.
  Bot uni `/etc/secrets/cookies.txt` dan **avtomatik** topadi (qo'shimcha sozlash shart emas).
- Render Secret File faqat o'qish uchun, yt-dlp esa cookie faylga qayta yozmoqchi bo'ladi —
  shuning uchun kod har ish uchun faylning **nusxasini** `workdir` ichiga oladi.
- ⚠️ cookies.txt — akkauntingiz sessiyasi. **GitHub'ga push qilmang** (`.gitignore` da bor),
  faqat `youtube.com` cookie'larini eksport qiling (brauzerning *inkognito* oynasida kirib, eksportdan so'ng
  oynani yoping), va iloji bo'lsa **alohida (ikkinchi darajali) Google akkaunt** ishlating:
  botdan foydalanilsa YouTube akkauntni cheklashi mumkin.
- Cookie'lar vaqt o'tib eskiradi. Bot YouTube bloklasa adminlarga xabar yuboradi (30 daqiqada 1 marta).
- `player_client` profillari: `YT_PLAYER_CLIENTS=web,android,ios` (cookies bo'lsa standart shu tartib;
  cookies yo'q bo'lsa `android,web,ios`). Hammasi bloklansa — avtomatik SoundCloud zaxira.

### 4) Free tarif cheklovlari
- 15 daqiqa so'rov bo'lmasa uxlaydi → UptimeRobot'da `https://<servis>.onrender.com/` ga har 5 daqiqada ping.
- Disk vaqtinchalik: qayta deploy'da SQLite (kesh, statistika) o'chadi. Doimiy saqlash uchun pullik Disk
  (`DB_PATH=/data/bot.db`) yoki tashqi baza kerak.
- `yt-dlp` tez eskiradi: YouTube ishlamay qolsa "Clear build cache & deploy" qiling.

### 5) Case-sensitivity (Windows/macOS → Linux)
Git katta-kichik harf o'zgarishini ba'zan ko'rmaydi. Papka nomini o'zgartirsangiz:
`git config core.ignorecase false` va `git mv Handlers handlers_tmp && git mv handlers_tmp handlers`.

## Sozlamalar (.env)
| O'zgaruvchi | Izoh |
|---|---|
| `PROTECT_CONTENT` | `true` — Telegram saqlash/forward'ni cheklaydi (faqat tinglash) |
| `LINK_MAX_DURATION` / `TRACK_MAX_DURATION` | video / qo'shiq uchun maks. soniya (900) |
| `MP3_BITRATE` | 192 |
| `COOKIES_FILE` | cookies yo'lini qo'lda ko'rsatish |
