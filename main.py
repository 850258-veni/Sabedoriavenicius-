import os
import hashlib
import binascii
import asyncio
from datetime import datetime
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import asyncpg
import uvicorn

app = FastAPI()

# --- CONFIGURAÇÃO ---
ADMIN_PASS = "SABEDORIA2026" 
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

pool = None

async def get_db():
    global pool
    if pool is None:
        try:
            pool = await asyncio.wait_for(asyncpg.create_pool(DATABASE_URL), timeout=10.0)
        except Exception as e:
            print(f"❌ ERRO NA LIGAÇÃO DB: {e}")
            return None
    return pool

# --- 🔐 SEGURANÇA ---
def gerar_hash_seguro(pin: str):
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', pin.encode(), salt, 100000)
    return binascii.hexlify(salt).decode() + ":" + binascii.hexlify(key).decode()

def verificar_pin_seguro(pin_digitado: str, hash_armazenado: str):
    try:
        salt_hex, key_hex = hash_armazenado.split(":")
        salt = binascii.unhexlify(salt_hex)
        key_original = binascii.unhexlify(key_hex)
        nova_key = hashlib.pbkdf2_hmac('sha256', pin_digitado.encode(), salt, 100000)
        return nova_key == key_original
    except: return False

# --- 🛠️ SETUP AUTOMÁTICO ---
@app.on_event("startup")
async def setup_db():
    db = await get_db()
    if db:
        async with db.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS lojas (id SERIAL PRIMARY KEY, nome TEXT, chave_trabalhador TEXT UNIQUE, pago BOOLEAN DEFAULT TRUE);
                CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, loja_id INT REFERENCES lojas(id), nome TEXT, pin_hash TEXT, UNIQUE(loja_id, nome));
                CREATE TABLE IF NOT EXISTS stock (id SERIAL PRIMARY KEY, loja_id INT REFERENCES lojas(id), produto TEXT, quantidade FLOAT DEFAULT 0, preco_custo FLOAT DEFAULT 0, UNIQUE(loja_id, produto));
                CREATE TABLE IF NOT EXISTS vendas_live (id SERIAL PRIMARY KEY, loja_id INT REFERENCES lojas(id), usuario_id INT REFERENCES usuarios(id), produto TEXT, quantidade FLOAT, preco FLOAT, preco_custo FLOAT, data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            """)

# --- INTERFACE VISUAL (CSS) ---
CSS = """<style>:root { --bg: #0a0a0a; --card: #141414; --primary: #ffb300; --success: #10b981; --danger: #ef4444; }
body { font-family: 'Segoe UI', sans-serif; background: var(--bg); color: #fff; padding: 15px; margin: 0; }
.card { background: var(--card); padding: 20px; border-radius: 15px; border: 1px solid #222; margin-bottom: 15px; max-width: 450px; margin: auto; }
input, button, select { width: 100%; padding: 14px; margin: 8px 0; border-radius: 10px; border: 1px solid #333; font-size: 16px; box-sizing: border-box; background: #1a1a1a; color: #fff; }
button { background: var(--primary); font-weight: bold; border: none; cursor: pointer; color: #000; }
.val { font-size: 24px; font-weight: bold; color: var(--success); }
.mini-text { font-size: 11px; color: #888; text-transform: uppercase; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
td, th { padding: 10px; border-bottom: 1px solid #222; text-align: left; }
</style>"""

# --- ROTAS PRINCIPAIS ---

@app.get("/", response_class=HTMLResponse)
async def home():
    return f"""<head><meta name='viewport' content='width=device-width, initial-scale=1'>{CSS}</head>
    <div class='card' style='text-align:center;'>
        <h1 style='color:var(--primary);'>SABEDORIA</h1>
        <form onsubmit='event.preventDefault(); location.href="/registrar?c=" + document.getElementById("chave").value.toUpperCase();'>
            <input type='text' id='chave' placeholder='CHAVE DA LOJA' required style='text-align:center;'>
            <button type='submit'>ENTRAR NO CAIXA</button>
            <button type='button' style='background:#222; color:#fff' onclick='location.href="/dashboard?c=" + document.getElementById("chave").value.toUpperCase();'>VER LUCRO</button>
        </form>
    </div>"""

@app.get("/registrar", response_class=HTMLResponse)
async def pagina_registo(c: str):
    db = await get_db()
    l = await db.fetchrow("SELECT id, nome, pago FROM lojas WHERE chave_trabalhador = $1", c.strip())
    if not l: return "❌ LOJA NÃO ENCONTRADA"
    if not l['pago']: return "❌ ACESSO BLOQUEADO PELO ADMINISTRADOR"
    produtos = await db.fetch("SELECT produto, quantidade FROM stock WHERE loja_id = $1 AND quantidade > 0", l['id'])
    opts = "".join([f"<option value='{p['produto']}'>{p['produto']} ({p['quantidade']})</option>" for p in produtos])
    return f"""<head><meta name='viewport' content='width=device-width, initial-scale=1'>{CSS}</head>
    <div class='card'><h3>{l['nome']}</h3>
    <form action='/vender' method='post'>
        <input type='hidden' name='c' value='{c}'>
        <input name='u' placeholder='Nome do Vendedor' required>
        <input name='pin' type='password' placeholder='PIN' required maxlength='4'>
        <select name='p' required><option value=''>Escolher Item...</option>{opts}</select>
        <input type='number' name='pr' step='0.1' placeholder='Preço de Venda' required>
        <button type='submit'>CONFIRMAR VENDA</button>
    </form></div>"""

@app.post("/vender")
async def vender(c:str=Form(...), u:str=Form(...), pin:str=Form(...), p:str=Form(...), pr:float=Form(...)):
    db = await get_db()
    try:
        l = await db.fetchrow("SELECT id FROM lojas WHERE chave_trabalhador = $1 AND pago = TRUE", c.strip())
        user = await db.fetchrow("SELECT id, pin_hash FROM usuarios WHERE loja_id = $1 AND nome = $2", l['id'], u.strip())
        if not user or not verificar_pin_seguro(pin, user['pin_hash']): return "❌ PIN INVÁLIDO"
        item = await db.fetchrow("SELECT quantidade, preco_custo FROM stock WHERE loja_id=$1 AND produto=$2", l['id'], p)
        async with db.transaction():
            await db.execute("UPDATE stock SET quantidade = quantidade - 1 WHERE loja_id=$1 AND produto=$2", l['id'], p)
            await db.execute("INSERT INTO vendas_live (loja_id, usuario_id, produto, quantidade, preco, preco_custo) VALUES ($1,$2,$3,1,$4,$5)", l['id'], user['id'], p, pr, item['preco_custo'])
        return RedirectResponse(url=f"/registrar?c={c}", status_code=303)
    except Exception as e: return f"❌ ERRO: {str(e)}"

# --- PAINÉIS DE GESTÃO ---

@app.get("/admin", response_class=HTMLResponse)
async def admin(senha: str = ""):
    if senha != ADMIN_PASS: return f"{CSS}<div class='card'><form><input name='senha' type='password' placeholder='Senha'><button>ENTRAR</button></form></div>"
    db = await get_db()
    lojas = await db.fetch("SELECT id, nome FROM lojas WHERE pago = TRUE")
    opts = "".join([f"<option value='{l['id']}'>{l['nome']}</option>" for l in lojas])
    return f"""<head><meta name='viewport' content='width=device-width, initial-scale=1'>{CSS}</head>
    <div class='card'><h3>Novo Usuário</h3>
    <form action='/add_u' method='post'><input type='hidden' name='s' value='{senha}'><select name='l_id'>{opts}</select><input name='n' placeholder='Nome'><input name='p' placeholder='PIN 4 Digitos'><button>CRIAR</button></form></div>
    <div class='card'><h3>Reposição de Stock</h3>
    <form action='/repor' method='post'><input type='hidden' name='s' value='{senha}'><select name='l_id'>{opts}</select><input name='p' placeholder='Produto'><input type='number' name='q' placeholder='Qtd'><input type='number' name='pc' step='0.1' placeholder='Custo Unitário'><button>REPOR</button></form></div>"""

@app.get("/super_admin", response_class=HTMLResponse)
async def super_admin(senha: str = ""):
    if senha != ADMIN_PASS: return f"{CSS}<div class='card'><form><input name='senha' type='password' placeholder='Acesso Mestre'><button>ENTRAR</button></form></div>"
    db = await get_db()
    lojas = await db.fetch("SELECT * FROM lojas ORDER BY id DESC")
    rows = "".join([f"<tr><td>{l['nome']}</td><td>{l['chave_trabalhador']}</td><td><form action='/toggle' method='post'><input type='hidden' name='s' value='{senha}'><input type='hidden' name='id' value='{l['id']}'><button style='background:{'var(--danger)' if l['pago'] else 'var(--success)'}; color:#fff;'>{('BLOQUEAR' if l['pago'] else 'ATIVAR')}</button></form></td></tr>" for l in lojas])
    return f"""<head><meta name='viewport' content='width=device-width, initial-scale=1'>{CSS}</head>
    <div class='card'><h3>🚀 Criar Nova Loja</h3>
    <form action='/nova_loja' method='post'><input type='hidden' name='s' value='{senha}'><input name='n' placeholder='Nome da Loja'><input name='c' placeholder='Chave (ex: BAR01)'><button>ATIVAR LOJA</button></form></div>
    <div class='card'><table><tr><th>Loja</th><th>Chave</th><th>Ação</th></tr>{rows}</table></div>"""

# --- ACÇÕES DE ADMIN ---
@app.post("/add_u")
async def add_u(s:str=Form(...), l_id:int=Form(...), n:str=Form(...), p:str=Form(...)):
    if s == ADMIN_PASS: await (await get_db()).execute("INSERT INTO usuarios (loja_id, nome, pin_hash) VALUES ($1,$2,$3)", l_id, n.strip(), gerar_hash_seguro(p))
    return RedirectResponse(f"/admin?senha={s}", status_code=303)

@app.post("/repor")
async def repor(s:str=Form(...), l_id:int=Form(...), p:str=Form(...), q:float=Form(...), pc:float=Form(...)):
    if s == ADMIN_PASS: await (await get_db()).execute("INSERT INTO stock (loja_id, produto, quantidade, preco_custo) VALUES ($1,$2,$3,$4) ON CONFLICT (loja_id, produto) DO UPDATE SET quantidade = stock.quantidade + EXCLUDED.quantidade, preco_custo = EXCLUDED.preco_custo", l_id, p.upper().strip(), q, pc)
    return RedirectResponse(f"/admin?senha={s}", status_code=303)

@app.post("/nova_loja")
async def nova_loja(s:str=Form(...), n:str=Form(...), c:str=Form(...)):
    if s == ADMIN_PASS: await (await get_db()).execute("INSERT INTO lojas (nome, chave_trabalhador, pago) VALUES ($1,$2,TRUE)", n.strip(), c.strip().upper())
    return RedirectResponse(f"/super_admin?senha={s}", status_code=303)

@app.post("/toggle")
async def toggle(s:str=Form(...), id:int=Form(...)):
    if s == ADMIN_PASS: await (await get_db()).execute("UPDATE lojas SET pago = NOT pago WHERE id = $1", id)
    return RedirectResponse(f"/super_admin?senha={s}", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(c: str, d: str = None):
    db = await get_db()
    l = await db.fetchrow("SELECT id, nome FROM lojas WHERE chave_trabalhador = $1 AND pago = TRUE", c.strip())
    if not l: return "❌ ACESSO NEGADO"
    data_alvo = d if d else datetime.now().strftime('%Y-%m-%d')
    vendas = await db.fetch("SELECT u.nome as func, v.produto, (v.preco - v.preco_custo) as lucro FROM vendas_live v JOIN usuarios u ON v.usuario_id = u.id WHERE v.loja_id = $1 AND DATE(v.data_venda AT TIME ZONE 'UTC' AT TIME ZONE '+02') = $2", l['id'], data_alvo)
    lucro = sum([v['lucro'] for v in vendas])
    return f"""<head><meta name='viewport' content='width=device-width, initial-scale=1'>{CSS}</head>
    <div class='card'><span class='mini-text'>Lucro em {data_alvo}</span><br><span class='val'>{lucro:.2f} MT</span></div>
    <div class='card'><table>{"".join([f"<tr><td>{v['func']}</td><td>{v['produto']}</td><td>{v['lucro']:.2f}</td></tr>" for v in vendas])}</table></div>"""

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
 
