# Duka — M-Pesa E-Commerce Store
### Flask · MongoDB Atlas · Safaricom Daraja STK Push · Vercel Serverless

---

## Project Structure

```
project/
├── api/
│   └── index.py          ← Flask app (Vercel entry-point)
├── templates/
│   ├── store.html         ← Customer storefront
│   └── admin.html         ← Admin dashboard
├── vercel.json            ← Vercel routing + env var references
├── requirements.txt       ← Python dependencies
└── README.md
```

---

## 1. MongoDB Atlas Setup

1. Create a free cluster at https://cloud.mongodb.com
2. Create a database user with read/write permissions
3. Whitelist all IPs: **0.0.0.0/0** (required for Vercel serverless)
4. Get your connection string:
   ```
   mongodb+srv://<user>:<password>@cluster0.xxxxx.mongodb.net/
   ```
5. The app auto-creates two collections:
   - `products` — your catalogue items
   - `orders`   — M-Pesa transaction records

---

## 2. Safaricom Daraja API Setup

### Sandbox (testing)
1. Register at https://developer.safaricom.co.ke
2. Create an app and note your **Consumer Key** & **Consumer Secret**
3. Use sandbox shortcode `174379` and the test passkey from the portal
4. Set `MPESA_BASE_URL` = `https://sandbox.safaricom.co.ke`

### Production (live)
1. Apply for a Go-Live shortcode via Safaricom
2. Set `MPESA_BASE_URL` = `https://api.safaricom.co.ke`
3. Use `CustomerBuyGoodsOnline` transaction type (already configured)

### Callback URL
- Must be **publicly accessible HTTPS** — your Vercel deployment URL works perfectly
- Format: `https://your-project.vercel.app/api/mpesa/callback`

---

## 3. Vercel Deployment

### a. Install Vercel CLI
```bash
npm i -g vercel
```

### b. Set environment secrets
```bash
vercel secrets add mongodb_uri       "mongodb+srv://user:pass@cluster.mongodb.net/"
vercel secrets add mongodb_db        "mpesa_store"
vercel secrets add flask_secret_key  "$(openssl rand -hex 32)"
vercel secrets add mpesa_base_url    "https://sandbox.safaricom.co.ke"
vercel secrets add mpesa_consumer_key    "YOUR_CONSUMER_KEY"
vercel secrets add mpesa_consumer_secret "YOUR_CONSUMER_SECRET"
vercel secrets add mpesa_shortcode   "174379"
vercel secrets add mpesa_passkey     "YOUR_PASSKEY"
vercel secrets add mpesa_callback_url "https://YOUR-PROJECT.vercel.app/api/mpesa/callback"
```

### c. Deploy
```bash
vercel --prod
```

---

## 4. Local Development

```bash
# Install deps
pip install -r requirements.txt

# Set env vars in a .env file or export them:
export MONGODB_URI="mongodb+srv://..."
export MONGODB_DB="mpesa_store"
export FLASK_SECRET_KEY="dev-secret"
export MPESA_BASE_URL="https://sandbox.safaricom.co.ke"
export MPESA_CONSUMER_KEY="..."
export MPESA_CONSUMER_SECRET="..."
export MPESA_SHORTCODE="174379"
export MPESA_PASSKEY="..."
export MPESA_CALLBACK_URL="https://YOUR-NGROK-URL/api/mpesa/callback"

# Run
python api/index.py
```

> **Tip:** Use [ngrok](https://ngrok.com/) to expose localhost for M-Pesa callbacks during development:
> ```bash
> ngrok http 5000
> # Use the https URL as MPESA_CALLBACK_URL
> ```

---

## 5. Architecture Notes

| Concern | Solution |
|---|---|
| Connection pool safety | Single global `_mongo_client`; reused across warm invocations |
| Missing env vars | `_env()` helper wraps `os.environ.get()` with empty-string fallback |
| BSON ObjectId | `_serialize()` converts all `ObjectId` → `str` before templates/JSON |
| Type safety | `float(str(value))` inside `try/except` on all numeric inputs |
| M-Pesa callback | `force=True` JSON parse; always returns HTTP 200 with ResultCode=0 |
| Status polling | `/api/checkout/status/<id>` returns `{status, mpesa_receipt, amount}` |
| Frontend UX | Native `fetch()` + `setInterval` at 3s; breaks on Paid/Failed |

---

## 6. Routes Reference

| Route | Method | Description |
|---|---|---|
| `/` | GET | Customer storefront |
| `/admin` | GET | Admin dashboard |
| `/admin/product` | POST | Add new product |
| `/api/checkout` | POST | Initiate STK Push |
| `/api/checkout/status/<id>` | GET | Poll order status |
| `/api/mpesa/callback` | POST | Safaricom webhook |

---

## 7. Switching to Production M-Pesa

1. Change `MPESA_BASE_URL` → `https://api.safaricom.co.ke`
2. Replace sandbox shortcode with your live **Till Number** or **Paybill**
3. Ensure your domain has a valid SSL certificate (Vercel provides this automatically)
4. Update `MPESA_CALLBACK_URL` to your production domain

---

*Built with Flask, PyMongo, and the Safaricom Daraja API.*
