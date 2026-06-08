"""
Duka — M-Pesa E-Commerce Store
Single-file Flask app for Vercel serverless (@vercel/python).
Templates are embedded as strings to avoid file-path issues in the sandbox.
"""

import os
import base64
import datetime
import requests
from bson import ObjectId
from flask import Flask, render_template_string, request, jsonify, redirect, url_for
from pymongo import MongoClient, DESCENDING

# ─────────────────────────────────────────────────────────────────────────────
# App bootstrap
# ─────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me-in-prod")

# ─────────────────────────────────────────────────────────────────────────────
# 1. Serverless-safe MongoDB connection pool (single global client)
# ─────────────────────────────────────────────────────────────────────────────
_mongo_client = None


def get_db():
    global _mongo_client
    if _mongo_client is None:
        uri = os.environ.get("MONGODB_URI", "")
        if not uri:
            raise RuntimeError("MONGODB_URI environment variable is not set.")
        _mongo_client = MongoClient(
            uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            maxPoolSize=10,
            retryWrites=True,
        )
    return _mongo_client[os.environ.get("MONGODB_DB", "mpesa_store")]


# ─────────────────────────────────────────────────────────────────────────────
# 2. Safe environment-variable helpers
# ─────────────────────────────────────────────────────────────────────────────
def _env(key, fallback=""):
    return os.environ.get(key) or fallback


MPESA_BASE_URL        = _env("MPESA_BASE_URL",        "https://sandbox.safaricom.co.ke")
MPESA_CONSUMER_KEY    = _env("MPESA_CONSUMER_KEY")
MPESA_CONSUMER_SECRET = _env("MPESA_CONSUMER_SECRET")
MPESA_SHORTCODE       = _env("MPESA_SHORTCODE",       "174379")
MPESA_PASSKEY         = _env("MPESA_PASSKEY")
MPESA_CALLBACK_URL    = _env("MPESA_CALLBACK_URL",    "https://your-domain.vercel.app/api/mpesa/callback")


# ─────────────────────────────────────────────────────────────────────────────
# Daraja helpers
# ─────────────────────────────────────────────────────────────────────────────
def _daraja_token():
    creds = base64.b64encode(
        f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}".encode()
    ).decode()
    r = requests.get(
        f"{MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials",
        headers={"Authorization": f"Basic {creds}"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _stk_password_and_timestamp():
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    raw = f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{ts}"
    pwd = base64.b64encode(raw.encode()).decode()
    return pwd, ts


# ─────────────────────────────────────────────────────────────────────────────
# 3. BSON → JSON-safe serialisation
# ─────────────────────────────────────────────────────────────────────────────
def _serialize(doc):
    out = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            out[k] = str(v)
        elif isinstance(v, datetime.datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


# ─────────────────────────────────────────────────────────────────────────────
# EMBEDDED TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────
STORE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Duka — Premium Store</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;800&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet"/>
  <style>
    :root {
      --bg:#0a0a0f; --surface:#13131a; --card:#1a1a25; --border:#2a2a3a;
      --accent:#00c853; --accent2:#ffd600; --text:#f0f0f5; --muted:#8888aa;
      --danger:#ff3d57; --radius:14px; --shadow:0 8px 40px rgba(0,0,0,.5);
    }
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
    body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden}
    nav{position:sticky;top:0;z-index:100;background:rgba(10,10,15,.85);backdrop-filter:blur(18px);
      border-bottom:1px solid var(--border);padding:0 2rem;display:flex;align-items:center;
      justify-content:space-between;height:64px}
    .nav-logo{font-family:'Playfair Display',serif;font-size:1.6rem;font-weight:800;letter-spacing:-.02em}
    .nav-logo span{color:var(--accent)}
    .nav-links a{color:var(--muted);text-decoration:none;font-size:.875rem;font-weight:500;
      margin-left:2rem;transition:color .2s}
    .nav-links a:hover{color:var(--text)}
    .hero{position:relative;padding:6rem 2rem 4rem;text-align:center;overflow:hidden}
    .hero::before{content:'';position:absolute;inset:0;
      background:radial-gradient(ellipse 80% 60% at 50% 0%,rgba(0,200,83,.12) 0%,transparent 70%);
      pointer-events:none}
    .hero h1{font-family:'Playfair Display',serif;font-size:clamp(2.5rem,6vw,4.5rem);
      font-weight:800;line-height:1.1;letter-spacing:-.03em}
    .hero h1 em{color:var(--accent);font-style:normal}
    .hero p{margin-top:1rem;color:var(--muted);font-size:1.1rem;max-width:480px;margin-inline:auto}
    .badge-mpesa{display:inline-flex;align-items:center;gap:.5rem;margin-top:1.5rem;
      background:rgba(0,200,83,.1);border:1px solid rgba(0,200,83,.3);border-radius:999px;
      padding:.4rem 1.1rem;font-size:.8rem;font-weight:600;color:var(--accent);
      letter-spacing:.05em;text-transform:uppercase}
    .badge-mpesa::before{content:'';width:8px;height:8px;border-radius:50%;
      background:var(--accent);animation:pulse 1.8s infinite}
    @keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(1.4)}}
    .grid-wrap{max-width:1200px;margin:0 auto;padding:2rem}
    .section-label{font-size:.7rem;font-weight:600;letter-spacing:.12em;text-transform:uppercase;
      color:var(--muted);margin-bottom:1.5rem}
    .products-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:1.5rem}
    .product-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
      overflow:hidden;transition:transform .25s,border-color .25s,box-shadow .25s}
    .product-card:hover{transform:translateY(-4px);border-color:rgba(0,200,83,.4);
      box-shadow:var(--shadow),0 0 0 1px rgba(0,200,83,.2)}
    .card-img{width:100%;aspect-ratio:4/3;object-fit:cover;background:var(--surface);display:block}
    .card-img-placeholder{width:100%;aspect-ratio:4/3;
      background:linear-gradient(135deg,var(--surface),var(--border));
      display:flex;align-items:center;justify-content:center;font-size:3rem}
    .card-body{padding:1.25rem}
    .card-title{font-family:'Playfair Display',serif;font-size:1.1rem;font-weight:600;
      line-height:1.3;margin-bottom:.4rem}
    .card-desc{color:var(--muted);font-size:.82rem;line-height:1.5;margin-bottom:1rem}
    .price-row{display:flex;align-items:baseline;gap:.6rem;margin-bottom:1.1rem}
    .price-before{color:var(--muted);font-size:.85rem;text-decoration:line-through;
      text-decoration-color:var(--danger)}
    .price-after{font-size:1.35rem;font-weight:700;color:var(--accent)}
    .savings-tag{font-size:.7rem;font-weight:600;background:rgba(255,214,0,.12);color:var(--accent2);
      border:1px solid rgba(255,214,0,.3);border-radius:999px;padding:.15rem .55rem}
    .btn-buy{width:100%;padding:.75rem;border:none;background:var(--accent);color:#000;
      font-family:'DM Sans',sans-serif;font-size:.9rem;font-weight:700;border-radius:8px;
      cursor:pointer;transition:background .2s,transform .15s;letter-spacing:.01em}
    .btn-buy:hover{background:#00e060;transform:scale(1.02)}
    .btn-buy:active{transform:scale(.98)}
    .empty{text-align:center;padding:5rem 2rem;color:var(--muted)}
    .empty .emoji{font-size:4rem;display:block;margin-bottom:1rem}
    .modal-overlay{display:none;position:fixed;inset:0;z-index:9000;
      background:rgba(0,0,0,.75);backdrop-filter:blur(6px);
      align-items:center;justify-content:center}
    .modal-overlay.active{display:flex}
    .modal-box{background:var(--card);border:1px solid var(--border);border-radius:20px;
      padding:2.5rem 2rem;width:min(92vw,400px);text-align:center;animation:slideUp .3s ease}
    @keyframes slideUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}
    .modal-spinner{width:52px;height:52px;border-radius:50%;border:3px solid var(--border);
      border-top-color:var(--accent);animation:spin 1s linear infinite;margin:0 auto 1.5rem}
    @keyframes spin{to{transform:rotate(360deg)}}
    .modal-title{font-family:'Playfair Display',serif;font-size:1.3rem;margin-bottom:.5rem}
    .modal-sub{color:var(--muted);font-size:.875rem;line-height:1.5}
    .modal-close{margin-top:1.5rem;background:none;border:1px solid var(--border);
      color:var(--muted);padding:.5rem 1.5rem;border-radius:8px;cursor:pointer;
      font-size:.85rem;font-family:'DM Sans',sans-serif;transition:border-color .2s,color .2s}
    .modal-close:hover{border-color:var(--muted);color:var(--text)}
    .success-icon{font-size:3.5rem;margin-bottom:1rem;display:block}
    .receipt-code{display:inline-block;margin-top:.75rem;background:rgba(0,200,83,.1);
      border:1px solid rgba(0,200,83,.3);border-radius:8px;padding:.5rem 1.2rem;
      font-family:monospace;font-size:1.1rem;color:var(--accent);letter-spacing:.05em}
    .phone-form{margin-top:1.5rem;text-align:left}
    .phone-form label{font-size:.8rem;font-weight:600;color:var(--muted);display:block;margin-bottom:.4rem}
    .phone-form input{width:100%;padding:.75rem 1rem;background:var(--surface);
      border:1px solid var(--border);border-radius:8px;color:var(--text);
      font-family:'DM Sans',sans-serif;font-size:1rem;outline:none;transition:border-color .2s}
    .phone-form input:focus{border-color:var(--accent)}
    .phone-form input::placeholder{color:var(--muted)}
    .btn-pay{width:100%;margin-top:1rem;padding:.8rem;background:var(--accent);border:none;
      border-radius:8px;color:#000;font-family:'DM Sans',sans-serif;font-size:.95rem;
      font-weight:700;cursor:pointer;transition:background .2s}
    .btn-pay:hover{background:#00e060}
    .btn-pay:disabled{background:var(--border);color:var(--muted);cursor:not-allowed}
    .form-error{color:var(--danger);font-size:.8rem;margin-top:.5rem;display:none}
    footer{text-align:center;padding:2rem;color:var(--muted);font-size:.78rem;
      border-top:1px solid var(--border);margin-top:4rem}
    @media(max-width:600px){nav{padding:0 1rem}.hero{padding:4rem 1rem 2.5rem}.grid-wrap{padding:1rem}}
  </style>
</head>
<body>
<nav>
  <div class="nav-logo">Duka<span>.</span></div>
  <div class="nav-links"><a href="/admin">Admin ↗</a></div>
</nav>
<section class="hero">
  <h1>Shop Smarter,<br>Pay with <em>M-Pesa</em></h1>
  <p>Seamless Lipa Na M-Pesa checkout — tap, PIN, done.</p>
  <div class="badge-mpesa">Daraja STK Push &nbsp;·&nbsp; Live Payments</div>
</section>
<main class="grid-wrap">
  <p class="section-label">— Featured Products</p>
  {% if products %}
  <div class="products-grid">
    {% for p in products %}
    <article class="product-card">
      {% if p.imageUrl %}
        <img class="card-img" src="{{ p.imageUrl }}" alt="{{ p.title }}" loading="lazy"
             onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"/>
        <div class="card-img-placeholder" style="display:none">🛒</div>
      {% else %}
        <div class="card-img-placeholder">🛒</div>
      {% endif %}
      <div class="card-body">
        <h2 class="card-title">{{ p.title }}</h2>
        <p class="card-desc">{{ p.description }}</p>
        <div class="price-row">
          {% if p.priceBefore and p.priceBefore > p.priceAfter %}
            <span class="price-before">KES {{ "{:,.0f}".format(p.priceBefore) }}</span>
          {% endif %}
          <span class="price-after">KES {{ "{:,.0f}".format(p.priceAfter) }}</span>
          {% if p.priceBefore and p.priceBefore > p.priceAfter %}
            <span class="savings-tag">SAVE {{ "{:.0f}".format(((p.priceBefore - p.priceAfter) / p.priceBefore) * 100) }}%</span>
          {% endif %}
        </div>
        <button class="btn-buy"
          onclick='openCheckout("{{ p._id }}","{{ p.title | e }}",{{ p.priceAfter }})'>
          Buy Now — KES {{ "{:,.0f}".format(p.priceAfter) }}
        </button>
      </div>
    </article>
    {% endfor %}
  </div>
  {% else %}
  <div class="empty">
    <span class="emoji">🏪</span>
    <h2>No products yet</h2>
    <p>Visit the <a href="/admin" style="color:var(--accent)">Admin panel</a> to add your first product.</p>
  </div>
  {% endif %}
</main>
<footer>© 2025 Duka. Powered by M-Pesa Daraja &amp; Flask.</footer>

<div class="modal-overlay" id="phoneModal">
  <div class="modal-box">
    <div class="modal-title" id="phoneModalTitle">Complete Purchase</div>
    <p class="modal-sub" id="phoneModalSub">Enter your Safaricom number to receive the payment prompt.</p>
    <div class="phone-form">
      <label for="phoneInput">M-Pesa Phone Number</label>
      <input type="tel" id="phoneInput" placeholder="07XXXXXXXX or 2547XXXXXXXX" maxlength="13"/>
      <div class="form-error" id="formError">Please enter a valid Kenyan phone number.</div>
      <button class="btn-pay" id="btnPay" onclick="submitCheckout()">Pay with M-Pesa</button>
    </div>
    <button class="modal-close" onclick="closeAll()">Cancel</button>
  </div>
</div>

<div class="modal-overlay" id="loadingModal">
  <div class="modal-box">
    <div class="modal-spinner"></div>
    <div class="modal-title">Check Your Phone</div>
    <p class="modal-sub">An M-Pesa STK push has been sent.<br>Enter your <strong>PIN</strong> to complete payment.</p>
    <p class="modal-sub" style="margin-top:.75rem;color:var(--accent);font-size:.8rem" id="pollingMsg">Verifying payment…</p>
    <button class="modal-close" onclick="closeAll()">Cancel</button>
  </div>
</div>

<div class="modal-overlay" id="successModal">
  <div class="modal-box">
    <span class="success-icon">✅</span>
    <div class="modal-title">Payment Confirmed!</div>
    <p class="modal-sub">Your order has been received. Thank you for shopping with Duka.</p>
    <div class="receipt-code" id="receiptCode">—</div><br/>
    <button class="modal-close" onclick="closeAll()"
      style="margin-top:1rem;border-color:var(--accent);color:var(--accent)">Continue Shopping</button>
  </div>
</div>

<script>
  let _cur={id:'',title:'',amount:0},_iv=null,_cid=null,_n=0;
  const MAX=60;
  function openCheckout(id,title,amount){
    _cur={id,title,amount};
    document.getElementById('phoneModalTitle').textContent='Buy: '+title;
    document.getElementById('phoneModalSub').textContent='KES '+amount.toLocaleString()+' — Enter your Safaricom number to pay.';
    document.getElementById('phoneInput').value='';
    document.getElementById('formError').style.display='none';
    const b=document.getElementById('btnPay');b.disabled=false;b.textContent='Pay with M-Pesa';
    show('phoneModal');
  }
  function show(id){
    ['phoneModal','loadingModal','successModal'].forEach(m=>document.getElementById(m).classList.remove('active'));
    if(id)document.getElementById(id).classList.add('active');
  }
  function closeAll(){show(null);if(_iv){clearInterval(_iv);_iv=null;}}
  async function submitCheckout(){
    const phone=document.getElementById('phoneInput').value.trim();
    if(!/^(07\d{8}|2547\d{8}|\+2547\d{8})$/.test(phone.replace(/\s/g,''))){
      document.getElementById('formError').style.display='block';return;
    }
    document.getElementById('formError').style.display='none';
    const b=document.getElementById('btnPay');b.disabled=true;b.textContent='Sending…';
    try{
      const r=await fetch('/api/checkout',{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({phone,product_id:_cur.id,amount:_cur.amount,description:_cur.title.substring(0,50)})});
      const d=await r.json();
      if(!r.ok||!d.success){alert('⚠ '+(d.error||'Payment initiation failed.'));b.disabled=false;b.textContent='Pay with M-Pesa';return;}
      _cid=d.checkout_id;_n=0;show('loadingModal');
      _iv=setInterval(async()=>{
        if(++_n>MAX){clearInterval(_iv);_iv=null;document.getElementById('pollingMsg').textContent='Timed out.';return;}
        document.getElementById('pollingMsg').textContent='Checking status… ('+_n+'/'+MAX+')';
        try{
          const s=await(await fetch('/api/checkout/status/'+_cid)).json();
          if(s.status==='Paid'){clearInterval(_iv);_iv=null;
            document.getElementById('receiptCode').textContent=s.mpesa_receipt?'Receipt: '+s.mpesa_receipt:'Payment received ✓';
            show('successModal');}
          else if(s.status==='Failed'){clearInterval(_iv);_iv=null;closeAll();alert('❌ Payment cancelled or failed.');}
        }catch(e){}
      },3000);
    }catch(e){alert('Network error.');b.disabled=false;b.textContent='Pay with M-Pesa';}
  }
</script>
</body>
</html>"""


ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Duka Admin — Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;800&family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet"/>
  <style>
    :root{--bg:#07080f;--surface:#0e0f1a;--card:#13141f;--border:#21223a;
      --accent:#00c853;--accent2:#ffd600;--text:#e8e8f0;--muted:#6b6b88;
      --danger:#ff3d57;--warn:#ffa726;--radius:12px}
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
    body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
    .sidebar{position:fixed;top:0;left:0;bottom:0;width:220px;background:var(--surface);
      border-right:1px solid var(--border);display:flex;flex-direction:column;
      padding:2rem 1.25rem;z-index:10}
    .logo{font-family:'Playfair Display',serif;font-size:1.5rem;font-weight:800;margin-bottom:2.5rem}
    .logo span{color:var(--accent)}
    .sidebar nav a{display:flex;align-items:center;gap:.7rem;color:var(--muted);text-decoration:none;
      font-size:.875rem;font-weight:500;padding:.6rem .75rem;border-radius:8px;
      transition:background .2s,color .2s;margin-bottom:.25rem}
    .sidebar nav a:hover,.sidebar nav a.active{background:rgba(0,200,83,.1);color:var(--accent)}
    .sidebar-foot{margin-top:auto;color:var(--muted);font-size:.75rem}
    .main{margin-left:220px;padding:2.5rem 2rem;min-height:100vh}
    .page-header{display:flex;align-items:center;gap:1rem;margin-bottom:2.5rem}
    .page-header h1{font-family:'Playfair Display',serif;font-size:1.9rem;font-weight:800}
    .page-badge{font-size:.7rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
      color:var(--accent);background:rgba(0,200,83,.1);border:1px solid rgba(0,200,83,.25);
      padding:.25rem .7rem;border-radius:999px}
    .stats-row{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));
      gap:1rem;margin-bottom:2.5rem}
    .stat-card{background:var(--card);border:1px solid var(--border);
      border-radius:var(--radius);padding:1.25rem 1.25rem 1rem}
    .stat-label{font-size:.7rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;
      color:var(--muted);margin-bottom:.4rem}
    .stat-value{font-size:1.9rem;font-weight:700;font-family:'Playfair Display',serif}
    .stat-value.green{color:var(--accent)}.stat-value.yellow{color:var(--accent2)}.stat-value.red{color:var(--danger)}
    .panel{background:var(--card);border:1px solid var(--border);
      border-radius:var(--radius);margin-bottom:2rem;overflow:hidden}
    .panel-header{display:flex;align-items:center;gap:1rem;padding:1.1rem 1.5rem;
      border-bottom:1px solid var(--border)}
    .panel-title{font-size:.85rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase}
    .panel-body{padding:1.5rem}
    .form-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
    .form-group{display:flex;flex-direction:column;gap:.4rem}
    .form-group.full{grid-column:1/-1}
    label{font-size:.78rem;font-weight:600;color:var(--muted);letter-spacing:.03em}
    input[type="text"],input[type="url"],input[type="number"],textarea{
      background:var(--surface);border:1px solid var(--border);border-radius:8px;
      padding:.7rem .9rem;color:var(--text);font-family:'DM Sans',sans-serif;
      font-size:.9rem;outline:none;transition:border-color .2s;width:100%}
    input:focus,textarea:focus{border-color:var(--accent)}
    input::placeholder,textarea::placeholder{color:var(--muted)}
    textarea{resize:vertical;min-height:80px}
    .btn-submit{margin-top:.5rem;padding:.8rem 2rem;background:var(--accent);border:none;
      border-radius:8px;color:#000;font-family:'DM Sans',sans-serif;font-size:.9rem;
      font-weight:700;cursor:pointer;transition:background .2s}
    .btn-submit:hover{background:#00e060}
    .flash{padding:.75rem 1rem;border-radius:8px;margin-bottom:1.5rem;font-size:.875rem}
    .flash.success{background:rgba(0,200,83,.1);border:1px solid rgba(0,200,83,.3);color:var(--accent)}
    .flash.error{background:rgba(255,61,87,.1);border:1px solid rgba(255,61,87,.3);color:var(--danger)}
    .table-wrap{overflow-x:auto}
    table{width:100%;border-collapse:collapse;font-size:.84rem}
    thead tr{border-bottom:2px solid var(--border)}
    thead th{text-align:left;padding:.75rem 1rem;font-size:.7rem;font-weight:700;
      letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
    tbody tr{border-bottom:1px solid var(--border);transition:background .15s}
    tbody tr:hover{background:rgba(255,255,255,.02)}
    tbody tr:last-child{border-bottom:none}
    td{padding:.8rem 1rem;vertical-align:middle}
    .mono{font-family:'DM Mono',monospace;font-size:.82rem;color:var(--muted)}
    .phone-cell{font-family:'DM Mono',monospace;font-size:.82rem}
    .badge{display:inline-flex;align-items:center;gap:.35rem;font-size:.72rem;font-weight:700;
      letter-spacing:.06em;text-transform:uppercase;padding:.25rem .65rem;border-radius:999px}
    .badge::before{content:'';width:6px;height:6px;border-radius:50%}
    .badge-pending{background:rgba(255,167,38,.12);color:var(--warn);border:1px solid rgba(255,167,38,.3)}
    .badge-pending::before{background:var(--warn);animation:pulse 1.8s infinite}
    .badge-paid{background:rgba(0,200,83,.1);color:var(--accent);border:1px solid rgba(0,200,83,.3)}
    .badge-paid::before{background:var(--accent)}
    .badge-failed{background:rgba(255,61,87,.1);color:var(--danger);border:1px solid rgba(255,61,87,.3)}
    .badge-failed::before{background:var(--danger)}
    @keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(1.5)}}
    .amount-cell{font-weight:600}
    .receipt-cell{font-family:'DM Mono',monospace;font-size:.8rem;color:var(--accent)}
    .empty-table{text-align:center;padding:3rem;color:var(--muted)}
    @media(max-width:768px){.sidebar{display:none}.main{margin-left:0;padding:1.5rem 1rem}
      .form-grid{grid-template-columns:1fr}.stats-row{grid-template-columns:1fr 1fr}}
  </style>
</head>
<body>
<aside class="sidebar">
  <div class="logo">Duka<span>.</span></div>
  <nav>
    <a href="/">🛒 &nbsp;Storefront</a>
    <a href="/admin" class="active">📊 &nbsp;Dashboard</a>
  </nav>
  <div class="sidebar-foot">Duka Admin v1.0<br>Daraja STK Push</div>
</aside>
<main class="main">
  <div class="page-header">
    <h1>Admin Dashboard</h1>
    <span class="page-badge">Live</span>
  </div>
  {% if request.args.get('success') %}
  <div class="flash success">✓ {{ request.args.get('success') }}</div>
  {% endif %}
  {% if request.args.get('error') %}
  <div class="flash error">✗ {{ request.args.get('error') }}</div>
  {% endif %}
  {% set paid_orders    = orders | selectattr('status','equalto','Paid')    | list %}
  {% set pending_orders = orders | selectattr('status','equalto','Pending') | list %}
  {% set failed_orders  = orders | selectattr('status','equalto','Failed')  | list %}
  {% set total_revenue  = paid_orders | sum(attribute='amount') %}
  <div class="stats-row">
    <div class="stat-card"><div class="stat-label">Total Orders</div><div class="stat-value">{{ orders|length }}</div></div>
    <div class="stat-card"><div class="stat-label">Revenue (KES)</div><div class="stat-value green">{{ "{:,.0f}".format(total_revenue) }}</div></div>
    <div class="stat-card"><div class="stat-label">Paid</div><div class="stat-value green">{{ paid_orders|length }}</div></div>
    <div class="stat-card"><div class="stat-label">Pending</div><div class="stat-value yellow">{{ pending_orders|length }}</div></div>
    <div class="stat-card"><div class="stat-label">Failed</div><div class="stat-value red">{{ failed_orders|length }}</div></div>
  </div>
  <div class="panel">
    <div class="panel-header"><span style="font-size:1.1rem">📦</span><span class="panel-title">Publish New Product</span></div>
    <div class="panel-body">
      <form method="POST" action="/admin/product">
        <div class="form-grid">
          <div class="form-group">
            <label>Product Title *</label>
            <input type="text" name="title" placeholder="e.g. Wireless Earbuds Pro" required/>
          </div>
          <div class="form-group">
            <label>Image URL</label>
            <input type="url" name="imageUrl" placeholder="https://…/image.jpg"/>
          </div>
          <div class="form-group">
            <label>Price Before (KES)</label>
            <input type="number" name="priceBefore" placeholder="5999" min="0" step="1"/>
          </div>
          <div class="form-group">
            <label>Sale Price / Price After (KES) *</label>
            <input type="number" name="priceAfter" placeholder="3499" min="0" step="1" required/>
          </div>
          <div class="form-group full">
            <label>Description</label>
            <textarea name="description" placeholder="Brief product description…"></textarea>
          </div>
        </div>
        <button type="submit" class="btn-submit">+ Publish Product</button>
      </form>
    </div>
  </div>
  <div class="panel">
    <div class="panel-header">
      <span style="font-size:1.1rem">💳</span>
      <span class="panel-title">M-Pesa Transactions</span>
      <span style="margin-left:auto;color:var(--muted);font-size:.8rem">{{ orders|length }} records</span>
    </div>
    <div class="table-wrap">
      {% if orders %}
      <table>
        <thead><tr>
          <th>Order ID</th><th>Phone</th><th>Amount (KES)</th>
          <th>Description</th><th>Status</th><th>Receipt</th><th>Date</th>
        </tr></thead>
        <tbody>
          {% for order in orders %}
          <tr>
            <td class="mono">{{ order._id[:8] }}…</td>
            <td class="phone-cell">{{ order.phone }}</td>
            <td class="amount-cell">{{ "{:,.0f}".format(order.amount) }}</td>
            <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted)">{{ order.description or '—' }}</td>
            <td>
              {% if order.status=='Paid' %}<span class="badge badge-paid">Paid</span>
              {% elif order.status=='Failed' %}<span class="badge badge-failed">Failed</span>
              {% else %}<span class="badge badge-pending">Pending</span>{% endif %}
            </td>
            <td class="receipt-cell">{{ order.mpesa_receipt or '—' }}</td>
            <td class="mono">{% if order.created_at %}{{ order.created_at[:16].replace('T',' ') }}{% else %}—{% endif %}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      {% else %}
      <div class="empty-table">
        <span style="font-size:2.5rem;display:block;margin-bottom:.75rem">📭</span>
        <p>No transactions yet.</p>
      </div>
      {% endif %}
    </div>
  </div>
</main>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/")
def storefront():
    try:
        db = get_db()
        products = [_serialize(p) for p in db.products.find().sort("_id", DESCENDING)]
    except Exception as exc:
        app.logger.error("DB error on storefront: %s", exc)
        products = []
    return render_template_string(STORE_HTML, products=products)


@app.route("/admin")
def admin():
    try:
        db = get_db()
        orders = [_serialize(o) for o in db.orders.find().sort("created_at", DESCENDING).limit(200)]
    except Exception as exc:
        app.logger.error("DB error on admin: %s", exc)
        orders = []
    return render_template_string(ADMIN_HTML, orders=orders, request=request)


@app.route("/admin/product", methods=["POST"])
def admin_add_product():
    try:
        db = get_db()
        price_before = float(request.form.get("priceBefore") or 0)
        price_after  = float(request.form.get("priceAfter")  or 0)
        doc = {
            "title":       request.form.get("title", "").strip(),
            "description": request.form.get("description", "").strip(),
            "imageUrl":    request.form.get("imageUrl", "").strip(),
            "priceBefore": price_before,
            "priceAfter":  price_after,
            "created_at":  datetime.datetime.utcnow(),
        }
        if not doc["title"]:
            return redirect("/admin?error=Title+is+required")
        db.products.insert_one(doc)
    except ValueError as exc:
        return redirect(f"/admin?error=Invalid+price+format")
    except Exception as exc:
        app.logger.error("Product insert error: %s", exc)
        return redirect("/admin?error=Database+error")
    return redirect("/admin?success=Product+added+successfully")


@app.route("/api/checkout", methods=["POST"])
def checkout():
    payload = request.get_json(force=True, silent=True) or {}
    try:
        amount      = int(float(str(payload.get("amount", 1))))
        phone       = str(payload.get("phone", "")).strip().replace("+", "")
        product_id  = str(payload.get("product_id", "")).strip()
        description = str(payload.get("description", "Order"))[:50]
    except (ValueError, TypeError) as exc:
        return jsonify({"error": f"Invalid input: {exc}"}), 400

    if not phone or not product_id:
        return jsonify({"error": "Phone and product_id are required."}), 400

    if phone.startswith("0"):
        phone = "254" + phone[1:]
    if not phone.startswith("254") or len(phone) != 12:
        return jsonify({"error": "Invalid Kenyan phone number. Use 07XXXXXXXX."}), 400

    try:
        db = get_db()
        result = db.orders.insert_one({
            "product_id": product_id, "phone": phone, "amount": amount,
            "description": description, "status": "Pending",
            "mpesa_receipt": None, "checkout_request_id": None,
            "created_at": datetime.datetime.utcnow(),
        })
        order_id = str(result.inserted_id)
    except Exception as exc:
        app.logger.error("Order insert error: %s", exc)
        return jsonify({"error": "Database error, please retry."}), 500

    try:
        token = _daraja_token()
        password, timestamp = _stk_password_and_timestamp()
        resp = requests.post(
            f"{MPESA_BASE_URL}/mpesa/stkpush/v1/processrequest",
            json={
                "BusinessShortCode": MPESA_SHORTCODE, "Password": password,
                "Timestamp": timestamp, "TransactionType": "CustomerBuyGoodsOnline",
                "Amount": amount, "PartyA": phone, "PartyB": MPESA_SHORTCODE,
                "PhoneNumber": phone, "CallBackURL": MPESA_CALLBACK_URL,
                "AccountReference": order_id, "TransactionDesc": description,
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        stk_data = resp.json()
        db.orders.update_one(
            {"_id": result.inserted_id},
            {"$set": {"checkout_request_id": stk_data.get("CheckoutRequestID", "")}},
        )
        return jsonify({"success": True, "checkout_id": order_id, "message": "STK Push sent."})
    except Exception as exc:
        db.orders.update_one({"_id": result.inserted_id}, {"$set": {"status": "Failed"}})
        app.logger.error("STK Push error: %s", exc)
        return jsonify({"error": "M-Pesa request failed. Check credentials or try again."}), 502


@app.route("/api/checkout/status/<checkout_id>")
def checkout_status(checkout_id):
    try:
        db = get_db()
        order = db.orders.find_one({"_id": ObjectId(checkout_id)})
        if not order:
            return jsonify({"error": "Order not found."}), 404
        return jsonify({
            "status": order.get("status", "Pending"),
            "mpesa_receipt": order.get("mpesa_receipt"),
            "amount": order.get("amount"),
        })
    except Exception as exc:
        app.logger.error("Status check error: %s", exc)
        return jsonify({"error": "Could not retrieve status."}), 500


@app.route("/api/mpesa/callback", methods=["POST"])
def mpesa_callback():
    try:
        data     = request.get_json(force=True, silent=True) or {}
        callback = data.get("Body", {}).get("stkCallback", {})
        result_code  = callback.get("ResultCode")
        checkout_req = callback.get("CheckoutRequestID", "")
        items        = callback.get("CallbackMetadata", {}).get("Item", [])
        receipt = next((i.get("Value") for i in items if i.get("Name") == "MpesaReceiptNumber"), None)
        amount  = None
        for i in items:
            if i.get("Name") == "Amount":
                try: amount = float(i.get("Value", 0))
                except: pass
        db = get_db()
        if result_code == 0:
            db.orders.update_one(
                {"checkout_request_id": checkout_req},
                {"$set": {"status": "Paid", "mpesa_receipt": receipt,
                           "paid_amount": amount, "paid_at": datetime.datetime.utcnow()}},
            )
        else:
            db.orders.update_one(
                {"checkout_request_id": checkout_req},
                {"$set": {"status": "Failed", "result_code": result_code}},
            )
    except Exception as exc:
        app.logger.error("Callback error: %s", exc)
    return jsonify({"ResultCode": 0, "ResultDescription": "Success"}), 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)
