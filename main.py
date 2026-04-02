import os
import hashlib
import binascii
from datetime import datetime
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import asyncpg
import uvicorn

app = FastAPI()

# --- CONFIGURAÇÃO E CONEXÃO ---
ADMIN_PASS = "SABEDORIA2026" 
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

pool = None
async def get_db():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(DATABASE_URL)
    return pool

# --- 🔐 SEGURANÇA: PBKDF2 + SALT ---
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
    except Exception:
        return False

# --- 🛠️ SETUP: ESTRUTURA ---
@app.on_event("startup")
async def setup_db():
    db = await get_db()
    await db.execute("""
        CREATE TABLE IF NOT EXISTS lojas (
            id SERIAL PRIMARY KEY, 
            nome TEXT, 
            chave_trabalhador TEXT UNIQUE, 
            pago BOOLEAN DEFAULT FALSE
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            loja_id INT REFERENCES lojas(id),
            nome TEXT,
            pin_hash TEXT,
            tentativas INT DEFAULT 0,
            bloqueado BOOLEAN DEFAULT FALSE,
            UNIQUE(loja_id, nome)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS stock (
            id SERIAL PRIMARY KEY,
            loja_id INT REFERENCES lojas(id),
            produto TEXT,
            quantidade FLOAT DEFAULT 0,
            preco_custo FLOAT DEFAULT 0,
            UNIQUE(loja_id, produto)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS vendas_live (
            id SERIAL PRIMARY KEY, 
            loja_id INT REFERENCES lojas(id), 
            usuario_id INT REFERENCES usuarios(id), 
            produto TEXT, 
            quantidade FLOAT, 
            preco FLOAT, 
            preco_custo FLOAT, 
            data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✅ SISTEMA CORRIGIDO E ONLINE!")

CSS = """<style>:root { --bg: #0a0a0a; --card: #141414; --primary: #ffb300; --success: #10b981; --danger: #ef4444; }
body { font-family: 'Segoe UI', sans-serif; background: var(--bg); color: #fff; padding: 15px; margin: 0; }
.card { background: var(--card); padding: 20px; border-radius: 15px; border: 1px solid #222; margin-bottom: 15px; max-width: 450px; margin: auto; }
input, button, select { width: 100%; padding: 14px; margin: 8px 0; border-radius: 10px; border: 1px solid #333; font-size: 16px; box-sizing: border-box; background: #1a1a1a; color: #fff; }
button { background: var(--primary); font-weight: bold; border: none; cursor: pointer; color: #000; }
.val { font-size: 24px; font-weight: bold; color: var(--success); }
.mini-text { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 1px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
td { padding: 12px 8px; border-bottom: 1px solid #222; }
</style>"""

@app.get("/", response_class=HTMLResponse)
async def home():
    return f"""<head><meta name='viewport' content='width=device-width, initial-scale=1'>{CSS}</head>
    <div class='card' style='text-align:center;'>
        <h1 style='color:var(--primary); margin:0;'>SABEDORIA</h1>
        <p class='mini-text'>Gestão de Lucro e Stock</p><br>
        <form onsubmit='event.preventDefault(); location.href="/registrar?c=" + document.getElementById("chave").value.toUpperCase();'>
            <input type='text' id='chave' placeholder='CHAVE DA LOJA' required style='text-align:center;'>
            <button type='submit'>ACEDER AO CAIXA</button>
            <button type='button' style='background:#222; color:#fff' onclick='location.href="/dashboard?c=" + document.getElementById("chave").value.toUpperCase();'>DASHBOARD</button>
        </form>
    </div>"""

@app.get("/registrar", response_class=HTMLResponse)
async def pagina_registo(c: str):
    db = await get_db()
    l = await db.fetchrow("SELECT id, nome, pago FROM lojas WHERE chave_trabalhador = $1", c.strip())
    if not l or not l['pago']: return "❌ ACESSO NEGADO"
    
    produtos = await db.fetch("SELECT produto, quantidade, preco_custo FROM stock WHERE loja_id = $1 AND quantidade > 0", l['id'])
    opts = "".join([f"<option value='{p['produto']}'>{p['produto']} (Disp: {p['quantidade']})</option>" for p in produtos])

    return f"""<head><meta name='viewport' content='width=device-width, initial-scale=1'>{CSS}</head>
    <div class='card'><h3>{l['nome']}</h3>
    <form action='/vender' method='post'>
        <input type='hidden' name='c' value='{c}'>
        <input name='u' placeholder='Nome do Funcionário' required>
        <input name='pin' type='password' placeholder='PIN' required maxlength='4'>
        <select name='p' required><option value=''>Escolher Produto...</option>{opts}</select>
        <input type='number' name='pr' step='0.1' placeholder='Preço de Venda' required>
        <button type='submit'>REGISTAR VENDA</button>
    </form></div>"""

@app.post("/vender")
async def processar_venda(c:str=Form(...), u:str=Form(...), pin:str=Form(...), p:str=Form(...), pr:float=Form(...)):
    db = await get_db()
    l = await db.fetchrow("SELECT id FROM lojas WHERE chave_trabalhador = $1", c.strip())
    if not l: return "❌ LOJA INVÁLIDA"

    user = await db.fetchrow("SELECT * FROM usuarios WHERE loja_id = $1 AND nome = $2", l['id'], u.strip())
    if not user or user['bloqueado']: return "❌ USUÁRIO BLOQUEADO OU INEXISTENTE"
    if not verificar_pin_seguro(pin, user['pin_hash']):
        await db.execute("UPDATE usuarios SET tentativas = tentativas + 1 WHERE id = $1", user['id'])
        if user['tentativas'] + 1 >= 3: await db.execute("UPDATE usuarios SET bloqueado = TRUE WHERE id = $1", user['id'])
        return "❌ PIN INCORRETO"
    
    item = await db.fetchrow("SELECT quantidade, preco_custo FROM stock WHERE loja_id=$1 AND produto=$2", l['id'], p)
    if not item or item['quantidade'] <= 0: return "❌ SEM STOCK"

    async with db.transaction():
        await db.execute("UPDATE stock SET quantidade = quantidade - 1 WHERE loja_id=$1 AND produto=$2", l['id'], p)
        await db.execute("INSERT INTO vendas_live (loja_id, usuario_id, produto, quantidade, preco, preco_custo) VALUES ($1, $2, $3, 1, $4, $5)", 
                         l['id'], user['id'], p, pr, item['preco_custo'])
        await db.execute("UPDATE usuarios SET tentativas = 0 WHERE id = $1", user['id'])
    
    return RedirectResponse(f"/registrar?c={c}", status_code=303)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(c: str, d: str = None):
    db = await get_db()
    l = await db.fetchrow("SELECT id, nome, pago FROM lojas WHERE chave_trabalhador = $1", c.strip())
    if not l or not l['pago']: return "❌ BLOQUEADO"
    
    data_alvo = d if d else datetime.now().strftime('%Y-%m-%d')
    vendas = await db.fetch("""
        SELECT u.nome as func, v.produto, (v.preco - v.preco_custo) as lucro 
        FROM vendas_live v JOIN usuarios u ON v.usuario_id = u.id 
        WHERE v.loja_id = $1 AND DATE(v.data_venda AT TIME ZONE 'UTC' AT TIME ZONE '+02') = $2
    """, l['id'], data_alvo)
    
    lucro_total = sum([v['lucro'] for v in vendas])
    return f"""<head><meta name='viewport' content='width=device-width, initial-scale=1'>{CSS}</head>
    <div class='card'><span class='mini-text'>Lucro Real {data_alvo}</span><br><span class='val'>{lucro_total:.2f} MT</span></div>
    <div class='card'><table>{"".join([f"<tr><td>{v['func']}</td><td>{v['produto']}</td><td>{v['lucro']:.2f}</td></tr>" for v in vendas]) or "Sem vendas."}</table>
    <form method='get' style='margin-top:10px;'><input type='hidden' name='c' value='{c}'><input type='date' name='d' value='{data_alvo}' onchange='this.form.submit()'></form>
    </div>"""

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(senha: str = ""):
    if senha != ADMIN_PASS: 
        return f"""<head><meta name='viewport' content='width=device-width, initial-scale=1'>{CSS}</head>
        <div class='card'><form><input name='senha' type='password' placeholder='Senha Mestra'><button>ENTRAR</button></form></div>"""
    
    db = await get_db()
    lojas = await db.fetch("SELECT id, nome FROM lojas")
    lojas_html = "".join([f"<option value='{l['id']}'>{l['nome']}</option>" for l in lojas])

    return f"""<head><meta name='viewport' content='width=device-width, initial-scale=1'>{CSS}</head>
    <div class='card'><h3>Criar Usuário</h3>
    <form action='/add_user' method='post'><input type='hidden' name='s' value='{senha}'>
    <select name='l_id'>{lojas_html}</select>
    <input name='n' placeholder='Nome'> <input name='p' placeholder='PIN'> <button>CRIAR</button></form></div>
    <div class='card'><h3>Reposição de Stock</h3>
    <form action='/repor' method='post'><input type='hidden' name='s' value='{senha}'>
    <select name='l_id'>{lojas_html}</select>
    <input name='p' placeholder='Produto'> <input type='number' name='q' placeholder='Qtd'> <input type='number' name='pc' step='0.1' placeholder='Custo Unitário'> <button>REPOR</button></form></div>"""

@app.post("/add_user")
async def add_user(s:str=Form(...), l_id:int=Form(...), n:str=Form(...), p:str=Form(...)):
    if s == ADMIN_PASS: await (await get_db()).execute("INSERT INTO usuarios (loja_id, nome, pin_hash) VALUES ($1, $2, $3)", l_id, n.strip(), gerar_hash_seguro(p))
    return RedirectResponse(f"/admin?senha={s}", status_code=303)

@app.post("/repor")
async def repor_stock(s:str=Form(...), l_id:int=Form(...), p:str=Form(...), q:float=Form(...), pc:float=Form(...)):
    if s == ADMIN_PASS:
        await (await get_db()).execute("""
            INSERT INTO stock (loja_id, produto, quantidade, preco_custo) VALUES ($1, $2, $3, $4)
            ON CONFLICT (loja_id, produto) DO UPDATE SET quantidade = stock.quantidade + EXCLUDED.quantidade, preco_custo = EXCLUDED.preco_custo
        """, l_id, p.upper().strip(), q, pc)
    return RedirectResponse(f"/admin?senha={s}", status_code=303)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
