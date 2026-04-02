import os, asyncio, uvicorn
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import asyncpg

app = FastAPI()
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

pool = None
async def get_db():
    global pool
    if pool is None: pool = await asyncpg.create_pool(DATABASE_URL)
    return pool

# --- CSS PROFISSIONAL PARA TELEMÓVEL ---
CSS = """<style>
:root { --bg: #0a0a0a; --card: #141414; --primary: #ffb300; --danger: #ef4444; --success: #10b981; }
body { font-family: sans-serif; background: var(--bg); color: #fff; margin: 0; padding: 10px; }
.card { background: var(--card); padding: 15px; border-radius: 12px; margin-bottom: 10px; border: 1px solid #222; }
input, button, select { width: 100%; padding: 12px; margin: 5px 0; border-radius: 8px; border: none; background: #1a1a1a; color: #fff; font-size: 16px; box-sizing: border-box; }
button { background: var(--primary); color: #000; font-weight: bold; cursor: pointer; }
.bar-bg { background: #333; height: 8px; border-radius: 4px; margin-top: 5px; }
.bar-fill { background: var(--primary); height: 100%; border-radius: 4px; }
.low { background: var(--danger) !important; }
</style>"""

@app.on_event("startup")
async def setup():
    db = await get_db()
    async with db.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS lojas (id SERIAL PRIMARY KEY, nome TEXT, chave_trabalhador TEXT UNIQUE, pago BOOLEAN DEFAULT TRUE);
            CREATE TABLE IF NOT EXISTS stock (id SERIAL PRIMARY KEY, loja_id INT REFERENCES lojas(id), produto TEXT, quantidade FLOAT DEFAULT 0, preco_custo FLOAT DEFAULT 0, UNIQUE(loja_id, produto));
            CREATE TABLE IF NOT EXISTS vendas_live (id SERIAL PRIMARY KEY, loja_id INT REFERENCES lojas(id), produto TEXT, quantidade FLOAT, preco FLOAT, data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        """)

# --- PÁGINA DE VENDA (HÍBRIDA) ---
@app.get("/registrar", response_class=HTMLResponse)
async def registrar(c: str):
    db = await get_db()
    l = await db.fetchrow("SELECT id, nome FROM lojas WHERE chave_trabalhador = $1 AND pago = TRUE", c.strip().upper())
    if not l: return "❌ LOJA BLOQUEADA OU NÃO ENCONTRADA"
    
    produtos = await db.fetch("SELECT produto, quantidade FROM stock WHERE loja_id = $1", l['id'])
    opts = "".join([f"<option value='{p['produto']}'>{p['produto']} ({int(p['quantidade'])} un)</option>" for p in produtos])
    
    return f"""{CSS}
    <div class='card'><h2>{l['nome']} - Caixa</h2>
    <form action='/vender' method='post'>
        <input type='hidden' name='c' value='{c}'>
        <p style='font-size:12px; color:#888;'>Escolha um item ou digite um novo (Venda Livre)</p>
        <input name='p' list='prod-list' placeholder='Produto ou Categoria' required>
        <datalist id='prod-list'>{opts}</datalist>
        <input type='number' name='pr' step='0.01' placeholder='Preço de Venda (MT)' required>
        <input type='number' name='q' value='1' placeholder='Quantidade'>
        <button type='submit'>REGISTAR VENDA</button>
    </form>
    <button onclick="location.href='/dashboard?c={c}'" style='background:#222; color:#fff; margin-top:10px;'>VER RELATÓRIO</button>
    </div>"""

@app.post("/vender")
async def vender(c:str=Form(...), p:str=Form(...), pr:float=Form(...), q:float=Form(...)):
    db = await get_db()
    async with db.acquire() as conn:
        l = await conn.fetchrow("SELECT id FROM lojas WHERE chave_trabalhador = $1", c.strip().upper())
        # Tenta abater do stock se o produto existir
        await conn.execute("UPDATE stock SET quantidade = quantidade - $1 WHERE loja_id=$2 AND produto=$3", q, l['id'], p.upper())
        # Grava a venda
        await conn.execute("INSERT INTO vendas_live (loja_id, produto, quantidade, preco) VALUES ($1,$2,$3,$4)", l['id'], p.upper(), q, pr)
    return RedirectResponse(f"/registrar?c={c}", status_code=303)

# --- DASHBOARD COM BARRAS DE PROGRESSO ---
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(c: str):
    db = await get_db()
    l = await db.fetchrow("SELECT id, nome FROM lojas WHERE chave_trabalhador = $1", c.strip().upper())
    estoque = await db.fetch("SELECT produto, quantidade FROM stock WHERE loja_id=$1 ORDER BY quantidade ASC", l['id'])
    
    html_estoque = "<div class='card'><h3>📦 Estado do Stock</h3>"
    for p in estoque:
        perc = min(100, max(0, p['quantidade']))
        cls = "low" if p['quantidade'] <= 5 else ""
        html_estoque += f"""
        <div style='margin-bottom:10px;'>
            <span style='font-size:14px;'>{p['produto']} ({int(p['quantidade'])} un)</span>
            <div class='bar-bg'><div class='bar-fill {cls}' style='width:{perc}%'></div></div>
        </div>"""
    html_estoque += "</div>"
    
    return f"{CSS}{html_estoque}<div class='card'><button onclick='history.back()'>VOLTAR</button></div>"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
 
