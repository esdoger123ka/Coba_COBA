# PBS Telegram Bot

Bot Telegram untuk rekap pekerjaan teknisi dan menyimpan data ke Google Sheets.

## Fitur
- Input pekerjaan step-by-step.
- Pilih segment dan jenis order (dengan bobot).
- Pilih teknisi dari daftar unit.
- Statistik harian dan bulanan per teknisi.

## Setup
1. Buat file `.env` dari `.env.example` dan isi:
   - `BOT_TOKEN`
   - `GS_WEBAPP_URL` (URL Web App Apps Script)
   - `TZ=Asia/Jakarta`
2. Pastikan Apps Script Web App sudah bisa menerima `POST` JSON.
3. Install dependency:

```bash
pip install -r requirements.txt
```

## Jalankan
```bash
python -m src.bot
```

## Google Sheets via Apps Script
Bot akan mengirim data ke Apps Script Web App, yang kemudian menulis ke Spreadsheet.
