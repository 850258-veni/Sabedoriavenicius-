import os
import pandas as pd
from fastapi import FastAPI, Form
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

# --- 🛠️ AUTO-SETUP DE BASE DE DADOS (ANTI-ERRO) ---
@app.on_event("startup")
async def setup_db():
    db = await get_db()
    # Criação de tabelas com sintaxe simplificada para o Render
    await db.execute("CREATE TABLE IF NOT EXISTS lojas (id SERIAL PRIMARY KEY, nome TEXT, gmail_dono TEXT UNIQUE, senha_hash TEXT, chave_trabalhador TEXT UNIQUE, pago BOOLEAN DEFAULT FALSE)")
    await db.execute("CREATE TABLE IF NOT EXISTS precos_padrao (id SERIAL PRIMARY KEY, loja_id INT, produto TEXT, preco_custo FLOAT, UNIQUE(loja_id, produto))")
    await db.execute("CREATE TABLE IF NOT EXISTS vendas_live (id SERIAL PRIMARY KEY, loja_id INT, produto TEXT, quantidade FLOAT, preco FLOAT, preco_custo FLOAT DEFAULT 0, data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    print("✅ SISTEMA SINCRONIZADO E ONLINE!")

# --- CSS PREMIUM MOBILE ---
CSS = """
<style>
    :root { --bg: #0a0a0a; --card: #141414; --primary: #ffb300; --success: #10b981; }
    body { font-family: sans-serif; background: var(--bg); color: #fff; padding: 15px; margin: 0; }
    .card { background: var(--card); padding: 20px; border-radius: 12px; border: 1px solid #222; margin-bottom: 15px; }
    input, button { width: 100%; padding: 12px; margin: 8px 0; border-radius: 8px; border: 1px solid #333; font-size: 16px; }
    input { background: #1a1a1a; color: #fff; }
    button { background: var(--primary); color: #000; font-weight: bold; border: none; cursor: pointer; }
    .stat { font-size: 12px; color: #888; text-transform: uppercase; }
    .val { font-size: 20px; font-weight: bold; color: var(--success); }
</style>
"""

# --- ROTA: REGISTO COM AUTO-CUSTO ---
@app.get("/registrar", response_class=HTMLResponse)
async def pagina_registo(c: str, p: str = None):
    db = await get_db()
    loja = await db.fetchrow("SELECT id FROM lojas WHERE chave_trabalhador=$1", c.strip())
    if not loja: return "❌ ACESSO NEGADO"

    custo_sugerido = 0.0
    if p:
        custo_sugerido = await db.fetchval("SELECT preco_custo FROM precos_padrao WHERE loja_id=$1 AND produto=$2", loja['id'], p.strip()) or 0.0

    return f"""
    <head><meta name="viewport" content="width=device-width, initial-scale=1">{CSS}</head>
    <div class="card">
        <h3>Nova Venda</h3>
        <form action="/registrar_venda" method="post">
            <input type="hidden" name="c" value="{c}">
            <label>Produto:</label>
            <input type="text" name="p" value="{p or ''}" placeholder="Nome do Produto" required 
                   onblur="if(this.value) window.location.href='/registrar?c={c}&p='+this.value">
            
            <label>Preço de Venda:</label>
            <input type="number" name="pr" step="0.1" required>

            <label style="color: var(--primary);">Custo Unitário (Sugerido):</label>
            <input type="number" name="pc" value="{custo_sugerido}" step="0.1" required>

            <button type="submit">CONFIRMAR REGISTO</button>
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
    if not loja: return "❌ ACESSO NEGADO"

    rows = await db.fetch("SELECT produto, preco, preco_custo FROM vendas_live WHERE loja_id=$1", loja['id'])
    if not rows: return f"{CSS}<div class='card'>Nenhuma venda ainda.</div>"

    df = pd.DataFrame([dict(r) for r in rows])
    df['lucro'] = df['preco'] - df['preco_custo']
    
    total_lucro = df['lucro'].sum()
    top_produto = df.groupby('produto')['lucro'].sum().idxmax()

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
    <div class="card">
        <span class="stat">Produto mais Lucrativo</span><br>
        <b style="color:var(--primary); font-size:18px;">{top_produto}</b>
    </div>
    """

# --- 🏁 INICIALIZAÇÃO PARA O RENDER (PORT BINDING) ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
 
