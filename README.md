# Kairozen SMM Panel

Full-stack SMM Panel (Flask + PostgreSQL) — homepage, user dashboard, admin panel, KHQR deposit, និង public API v2 សម្រាប់ភ្ជាប់ bot/reseller។

## Project Structure

```
kairozen-smm-panel/
├── app.py                  # App factory + CLI commands
├── config.py                # Config from env vars
├── extensions.py            # db, login_manager
├── models.py                 # User, Service, Order, Deposit, AdminLog
├── requirements.txt
├── .env.example              # copy → .env ហើយបំពេញ
├── blueprints/
│   ├── public.py             # / (homepage)
│   ├── auth.py                # /auth/login, /auth/register, /auth/logout
│   ├── dashboard.py           # /dashboard/* (user)
│   ├── admin.py                # /admin/* (admin only)
│   └── api.py                  # /api/v2 (public API for bots/resellers)
├── services/
│   ├── provider.py             # khmer-smm.com proxy client
│   ├── khqr.py                  # Bakong EMV QR builder + payment check
│   └── pricing.py                # markup calculation
├── templates/                    # Jinja2, organized by blueprint
└── static/{css,js}
```

## Setup (local / Termux)

```bash
cd kairozen-smm-panel
pip install -r requirements.txt --break-system-packages   # Termux
# pip install -r requirements.txt                          # server ធម្មតា

cp .env.example .env
nano .env   # បំពេញ DATABASE_URL, PROVIDER_API_KEY, BAKONG_ACCOUNT_ID, ល.

export FLASK_APP=app.py
flask init-db        # បង្កើត tables
flask create-admin   # bootstrap admin account ពី .env (ADMIN_USERNAME/PASSWORD)

python app.py         # dev server :5000
# ឬ production:
gunicorn -w 2 -b 0.0.0.0:5000 app:app
```

## Database

ត្រូវការ **PostgreSQL** (តាមការសម្រេចចិត្ត)។ កំណត់ `DATABASE_URL` ក្នុង `.env`:
```
DATABASE_URL=postgresql://user:password@host:5432/dbname
```
បើដាក់ deploy លើ Railway/Render — ប្រើ connection string ដែលគេ provide ឲ្យដោយផ្ទាល់ (កូដខាងក្នុង `config.py` handle ករណី `postgres://` legacy prefix ស្វ័យប្រវត្តិ)។

SQLite ប្រើជា fallback ស្វ័យប្រវត្តិបើគ្មាន `DATABASE_URL` (សម្រាប់សាកល្បងលឿនៗតែប៉ុណ្ណោះ មិនណែនាំសម្រាប់ production ទេ ព្រោះ multi-process write មិនមាំទាន់)។

## Environment Variables សំខាន់ៗ

| Variable | ន័យ |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `PROVIDER_API_URL` / `PROVIDER_API_KEY` | khmer-smm.com API (ត្រូវដាក់ key ផ្ទាល់ខ្លួន) |
| `DEFAULT_MARKUP_PERCENT` | % បន្ថែមលើ provider rate (admin អាច override ក្នុង UI ក៏បាន) |
| `BAKONG_ACCOUNT_ID` | គណនី Bakong ទទួលលុយ (Tag 30 — individual account) |
| `BAKONG_API_TOKEN` | Official Bakong API token (សម្រាប់ auto-check payment; បើ unauthorized admin confirm ដោយដៃនៅ `/admin/deposits`) |
| `APP_BASE_URL` | domain ពិតប្រាកដ (បង្ហាញក្នុង API docs page) |
| `ADMIN_USERNAME/EMAIL/PASSWORD` | admin bootstrap (តែម្តងគត់ តាមរយៈ `flask create-admin`) |

## សំខាន់ៗត្រូវដឹង

1. **Admin URL**: `/admin` (តម្រូវ login ដោយ account ដែលមាន `is_admin=True`)។
2. **Service sync**: Admin → Services → "Sync ពី khmer-smm.com" — service ថ្មីៗនឹង **inactive ដោយដែលក**, admin ត្រូវកំណត់ markup ហើយ tick Active ដើម្បីបង្ហាញលើ user។
3. **Public API** (`/api/v2`): User generate API key ផ្ទាល់ខ្លួននៅ Dashboard → API Key។ Format ដូច khmer-smm.com (`action=services/add/status/balance`) — ដូច្នេះ bot ឬ script ដែលគាំទ្រ provider format ស្តង់ដារ អាចភ្ជាប់ចូលផ្ទាល់។
4. **KHQR Payment check**: បើ `BAKONG_API_TOKEN` invalid/unauthorized (ដែលធ្លាប់ជួបពីមុន) ប្រព័ន្ធនឹង fail soft ហើយ deposit status នៅ pending — admin confirm ដោយដៃនៅ `/admin/deposits`។
5. **Balance flow**: កាត់ balance មុនបញ្ជូន order ទៅ provider; បើ provider បរាជ័យ refund ស្វ័យប្រវត្តិ។

## មិនទាន់បានធ្វើ (Next Steps ផ្ដល់យោបល់)

- Rate limiting លើ `/api/v2` (បច្ចុប្បន្នមិនទាន់កំណត់ request/min)
- Email verification ពេល register
- Webhook ពី khmer-smm.com (បច្ចុប្បន្ន user ត្រូវ click "Refresh" ដើម្បីទាញ status ថ្មី — អាចប្រើ cron job polling ជំនួសវិញ)
- Multi-currency (បច្ចុប្បន្នតែ USD)
