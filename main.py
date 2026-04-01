import os
import pandas as pd
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from passlib.context import CryptContext
import asyncpg
import uvicorn

app = FastAPI()

# --- CONFIGURAÇÃO DE AMBIENTE ---
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

pool = None

async def get_db():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(DATABASE_URL)
    return pool

# --- 🛠️ AUTO-SETUP (MIGRATIONS) ---
@app.on_event("startup")
async def setup_db():
    db = await get_db()
    await db.execute("CREATE TABLE IF NOT EXISTS lojas (id SERIAL PRIMARY KEY, nome TEXT, gmail_dono TEXT UNIQUE, senha_hash TEXT, chave_trabalhador TEXT UNIQUE, pago BOOLEAN DEFAULT FALSE)")
    await db.execute("CREATE TABLE IF NOT EXISTS precos_padrao (id SERIAL PRIMARY KEY, loja_id INT, produto TEXT, preco_custo FLOAT, UNIQUE(loja_id, produto))")
    await db.execute("CREATE TABLE IF NOT EXISTS vendas_live (id SERIAL PRIMARY KEY, loja_id INT, produto TEXT, quantidade FLOAT, preco FLOAT, preco_custo FLOAT DEFAULT 0, data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    print("✅ SISTEMA ONLINE EM TETE!")

# --- CSS PREMIUM MOBILE ---
CSS = """
<style>
    :root { --bg: #0a0a0a; --card: #141414; --primary: #ffb300; --success: #10b981; }
    body { font-family: sans-serif; background: var(--bg); color: #fff; padding: 15px; margin: 0; text-align: center; }
    .card { background: var(--card); padding: 25px; border-radius: 15px; border: 1px solid #222; margin-bottom: 15px; max-width: 400px; margin-left: auto; margin-right: auto; }
    input, button { width: 100%; padding: 15px; margin: 10px 0; border-radius: 10px; border: 1px solid #333; font-size: 16px; box-sizing: border-box; }
    input { background: #1a1a1a; color: #fff; }
    button { background: var(--primary); color: #000; font-weight: bold; border: none; cursor: pointer; }
    .btn-dash { background: #333; color: #fff; margin-top: 5px; }
    .stat { font-size: 12px; color: #888; text-transform: uppercase; }
    .val { font-size: 22px; font-weight: bold; color: var(--success); }
</style>
"""

# --- 🏠 NOVA PORTA DE ENTRADA (HOME) ---
@app.get("/", response_class=HTMLResponse)
async def home():
    return f"""
    <head><meta name="viewport" content="width=device-width, initial-scale=1">{CSS}</head>
    <div class="card">
        <h1 style="color:var(--primary); margin-bottom:5px;">SABEDORIA</h1>
        <p style="color:#888; margin-top:0;">Gestão de Lucro Real - Tete</p>
        <hr style="border:0; border-top:1px solid #333; margin:20px 0;">
        
        <form onsubmit="event.preventDefault(); window.location.href='/registrar?c=' + document.getElementById('chave').value;">
            <label style="font-size:14px; display:block; text-align:left;">Introduza a sua Chave:</label>
            <input type="text" id="chave" placeholder="Ex: LOJA01" required>
            <button type="submit">ENTRAR PARA VENDER</button>
            <button type="button" class="btn-dash" onclick="window.location.href='/dashboard?c=' + document.getElementById('chave').value;">VER MEU LUCRO</button>
        </form>
    </div>
    """

# --- ROTA: REGISTO COM AUTO-CUSTO ---
@app.get("/registrar", response_class=HTMLResponse)
async def pagina_registo(c: str, p: str = None):
    db = await get_db()
    loja = await db.fetchrow("SELECT id FROM lojas WHERE chave_trabalhador=$1", c.strip())
    if not loja: return "❌ CHAVE INVÁLIDA"

    custo_sugerido = 0.0
    if p:
        custo_sugerido = await db.fetchval("SELECT preco_custo FROM precos_padrao WHERE loja_id=$1 AND produto=$2", loja['id'], p.strip()) or 0.0

    return f"""
    <head><meta name="viewport" content="width=device-width, initial-scale=1">{CSS}</head>
    <div class="card">
        <h3>Nova Venda: {loja['nome'] if 'nome' in loja else ''}</h3>
        <form action="/registrar_venda" method="post">
            <input type="hidden" name="c" value="{c}">
            <label>Produto:</label>
            <input type="text" name="p" value="{p or ''}" placeholder="Nome do Produto" required 
                   onblur="if(this.value) window.location.href='/registrar?c={c}&p='+this.value">
            
            <label>Preço de Venda:</label>
            <input type="number" name="pr" step="0.1" required>

            <label style="color: var(--primary);">Custo Unitário:</label>
            <input type="number" name="pc" value="{custo_sugerido}" step="0.1" required>

            <button type="submit">CONFIRMAR REGISTO</button>
            <button type="button" class="btn-dash" onclick="window.location.href='/'">SAIR / VOLTAR</button>
        </form>
    </div>
    """

# --- ROTA: PROCESSAR E SALVAR ---
@app.post("/registrar_venda")
async def registrar_venda(c:str=Form(...), p:str=Form(...), pr:float=Form(...), pc:float=Form(...)):
    db = await get_db()
    loja = await db.fetchrow("SELECT id FROM lojas WHERE chave_trabalhador=$1", c.strip())
    if not loja: return "❌ ERRO"

    await db.execute("INSERT INTO vendas_live (loja_id, produto, quantidade, preco, preco_custo) VALUES ($1, $2, 1, $3, $4)", loja['id'], p, pr, pc)
    await db.execute("INSERT INTO precos_padrao (loja_id, produto, preco_custo) VALUES ($1, $2, $3) ON CONFLICT (loja_id, produto) DO UPDATE SET preco_custo = EXCLUDED.preco_custo", loja['id'], p, pc)
    
    return RedirectResponse(url=f"/registrar?c={c}", status_code=303)

# --- ROTA: DASHBOARD DE LUCRO REAL ---
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(c:str):
    db = await get_db()
    loja = await db.fetchrow("SELECT id, nome FROM lojas WHERE chave_trabalhador=$1", c.strip())
    if not loja: return "❌ CHAVE INVÁLIDA"

    rows = await db.fetch("SELECT produto, preco, preco_custo FROM vendas_live WHERE loja_id=$1", loja['id'])
    if not rows: return f"{CSS}<div class='card'>Nenhuma venda. <br><br> <button onclick='window.history.back()'>VOLTAR</button></div>"

    df = pd.DataFrame([dict(r) for r in rows])
    df['lucro'] = df['preco'] - df['preco_custo']
    total_lucro = df['lucro'].sum()

    return f"""
    <head><meta name="viewport" content="width=device-width, initial-scale=1">{CSS}</head>
    <div class="card">
        <span class="stat">Negócio</span>
        <h2 style="margin:0;">{loja['nome']}</h2>
    </div>
    <div class="card">
        <span class="stat">Lucro Líquido Total</span><br>
        <span class="val">{total_lucro:.2f} MT</span>
    </div>
    <button onclick="window.history.back()">VOLTAR</button>
    """

# --- 🏁 INICIALIZAÇÃO ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
