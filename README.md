# 🎮 Minecraft Bedrock Addons — Telegram Bot

Minecraft Bedrock uchun addon, mod, shader, xarita va resource pack'lar katalogi.
Python 3.10+, **aiogram 3.x**, **aiosqlite** (SQLite), **python-dotenv**.

Botning barcha interfeysi **o'zbek tilida (lotin alifbosi)**.

---

## ✨ Imkoniyatlar

| Bo'lim | Tavsif |
|---|---|
| 📦 Barcha modlar / 🏆 Mashhur / 🆕 Yangi | Sahifalangan ro'yxatlar |
| 🔍 Mod qidirish | Nom, kalit so'z, qisman moslik, imlo xatolariga chidamli; kategoriya va versiya filtri |
| 📂 Kategoriyalar | 14 ta tayyor kategoriya (modlar soni bilan) |
| 🎮 Minecraft versiyalari | Foydalanuvchi o'z versiyasini tanlaydi; modlar ✅ / ⚠️ / ❌ bilan belgilanadi |
| ⭐ Sevimlilar | Har bir foydalanuvchi uchun alohida |
| ⬇️ Yuklab olish | Telegram `file_id` orqali (fayl serverga yuklanmaydi), yuklashlar hisoblanadi |
| 💡 Mod so'rash | Spam va takroriy so'rovlardan himoya; adminlar ko'rib chiqadi, foydalanuvchiga xabar boradi |
| 🛠 Admin panel | Mod qo'shish / tahrirlash / o'chirish, statistika, so'rovlarni boshqarish |

Qo'llab-quvvatlanadigan fayl turlari: `.mcaddon`, `.mcpack`, `.mcworld`, `.zip`.

---

## 🪟 Windows'da o'rnatish

### 1. Python o'rnatish
1. https://www.python.org/downloads/ saytidan **Python 3.10 yoki yangi** versiyasini yuklab oling.
2. O'rnatishda **«Add python.exe to PATH»** katagini albatta belgilang.
3. Tekshirish: `cmd` oynasida `python --version`

### 2. Bot yaratish
1. Telegram'da **@BotFather** ga `/newbot` yuboring va ko'rsatmalarga amal qiling.
2. Berilgan **tokenni** saqlab qo'ying.
3. O'zingizning Telegram ID raqamingizni **@userinfobot** orqali bilib oling (bu admin ID bo'ladi).

### 3. Loyihani tayyorlash
`cmd` yoki PowerShell'da loyiha papkasiga o'ting:

```bat
cd C:\yo'l\project
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 4. `.env` faylini sozlash
```bat
copy .env.example .env
notepad .env
```
Faylda quyidagilarni to'ldiring:

```env
BOT_TOKEN=123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ADMIN_IDS=123456789
```
Bir nechta admin bo'lsa, vergul bilan ajrating: `ADMIN_IDS=111111,222222`

Ixtiyoriy sozlamalar (`.env.example` ichida):

| O'zgaruvchi | Standart | Ma'nosi |
|---|---|---|
| `DB_PATH` | `data/bot.db` | Ma'lumotlar bazasi fayli |
| `MAX_FILE_MB` | `100` | Admin yuklaydigan fayl uchun maksimal hajm |
| `MC_VERSIONS` | `1.21,1.20,1.19,1.18,1.17,1.16` | Tanlanadigan Bedrock versiyalari (yangi versiya chiqsa shu yerga qo'shing) |
| `REQUEST_DAILY_LIMIT` | `3` | Bir foydalanuvchining kunlik mod so'rovlari soni |

### 5. Ishga tushirish
```bat
venv\Scripts\activate
python bot.py
```
Konsolda `Bot ishga tushdi: @sizning_botingiz` yozuvi chiqsa, bot ishlayapti.
To'xtatish: `Ctrl + C`.

> Keyingi safar faqat `venv\Scripts\activate` va `python bot.py` kifoya.
> Ma'lumotlar bazasi (`data/bot.db`) birinchi ishga tushirishda avtomatik yaratiladi.

---

## 🛠 Admin qo'llanmasi

Admin panelni ochish: **/admin** buyrug'i yoki bosh menyudagi **«🛠 Admin panel»** tugmasi
(tugma faqat `ADMIN_IDS` dagi foydalanuvchilarga ko'rinadi).

### ➕ Mod qo'shish (8 qadam)
1. **Nomi** (2–60 belgi)
2. **Tavsifi** (maks. 500 belgi)
3. **Kategoriya** — tugmalardan tanlanadi
4. **Muallif** (maks. 40 belgi)
5. **Minecraft versiyalari** — mos versiyalarni belgilang, so'ng «✔️ Tayyor».
   Hech narsa tanlanmasa, mod «⚠️ moslik tekshirilmagan» deb belgilanadi.
6. **Preview rasmi** — oddiy **foto** sifatida yuboring (fayl sifatida emas)
7. **Mod fayli** — `.mcaddon`, `.mcpack`, `.mcworld` yoki `.zip` ni **fayl (document)** sifatida yuboring
8. **O'rnatish yo'riqnomasi** — matn yuboring yoki «⏭ Standart yo'riqnoma» tugmasini bosing

Istalgan paytda **«❌ Bekor qilish»** tugmasi yoki **/cancel** bilan to'xtatish mumkin.

### ✏️ Tahrirlash va o'chirish
**✏️ Modlarni boshqarish** → modni tanlang → nomi, tavsifi, muallifi, kategoriyasi, versiyalari,
yo'riqnomasi, preview rasmi yoki faylini almashtiring. O'chirish — «🗑 O'chirish» (tasdiqlash so'raladi).
Oddiy foydalanuvchi ko'rinishidagi mod kartasida adminlar uchun «✏️ Tahrirlash» tugmasi ham bor.

### 📨 Mod so'rovlari
**📨 So'rovlar** → holat bo'yicha ro'yxat (Kutilmoqda / Tasdiqlangan / Rad etilgan / Bajarilgan).
So'rovni oching va **✅ Tasdiqlash**, **❌ Rad etish** yoki **🎉 Bajarildi** ni bosing —
foydalanuvchiga avtomatik xabar yuboriladi. Yangi so'rov kelganda adminlarga bildirishnoma keladi.

### 📊 Statistika
Foydalanuvchilar, modlar soni, jami / bugungi / 7 kunlik yuklashlar, kutilayotgan so'rovlar va eng ko'p yuklangan 10 ta mod.

---

## 🔒 Xavfsizlik

- `BOT_TOKEN` faqat `.env` faylida saqlanadi (`.env` ni hech kimga bermang va Git'ga yuklamang).
- Barcha admin funksiyalari `ADMIN_IDS` bo'yicha filtr bilan himoyalangan.
- Fayllar turi va hajmi tekshiriladi; fayllar **yuklab olinmaydi** va **ishga tushirilmaydi** —
  faqat Telegram `file_id` saqlanadi, xotira ishlatilmaydi.
- Rate limit: bir foydalanuvchidan 10 soniyada 15 tadan ortiq harakat qabul qilinmaydi.
- Mod so'rovlari: havolalar taqiqlangan, kunlik limit, 1 daqiqalik pauza, takroriy so'rovlar aniqlanadi.
- Barcha SQL so'rovlar parametrlashtirilgan, `PRAGMA foreign_keys = ON`.

---

## 📁 Loyiha tuzilmasi

```
project/
├── bot.py                 # ishga tushirish
├── config.py              # sozlamalar (.env)
├── requirements.txt
├── .env.example
├── database/
│   ├── db.py              # ulanish, sxema, yozish yordamchilari
│   └── queries.py         # barcha SQL so'rovlari
├── handlers/
│   ├── common.py          # /start, menyu, yordam, bekor qilish
│   ├── catalog.py         # ro'yxatlar, qidiruv, versiyalar, kartochka, sevimlilar, yuklash
│   ├── mod_requests.py    # foydalanuvchi so'rovlari
│   ├── admin.py           # admin panel
│   └── fallback.py        # noma'lum tugma/xabarlar
├── keyboards/             # inline klaviaturalar (foydalanuvchi va admin)
├── services/              # qidiruv, fayl tekshiruvi
├── states/                # FSM holatlari
└── utils/                 # matnlar (o'zbekcha), filtrlar, middleware, yordamchilar
```

---

## ❓ Tez-tez uchraydigan muammolar

| Muammo | Yechim |
|---|---|
| `BOT_TOKEN topilmadi` | `.env` fayli bormi va ichida `BOT_TOKEN=...` yozilganmi? |
| Admin panel ochilmayapti | `ADMIN_IDS` ga o'zingizning to'g'ri ID raqamingizni yozing va botni qayta ishga tushiring |
| `Unauthorized` xatosi | Token noto'g'ri — @BotFather'dan qayta oling |
| Fayl yuborilmayapti («Faylni yuborib bo'lmadi») | Fayl boshqa bot orqali yuklangan bo'lishi mumkin: modni shu bot orqali qayta yuklang («📦 Fayl» tugmasi) |
| Admin fayl yuklayotganda «juda katta» | `.env` da `MAX_FILE_MB` ni oshiring |
| Bot javob bermayapti | Konsolda xatolik bormi? Faqat bitta `python bot.py` nusxasi ishlayotganini tekshiring |

> ⚠️ Faqat administratorlar yuklagan yoki ruxsat etilgan manbalardagi fayllarni tarqating.
