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

# --- CSS PARA TELEMÓVEL ---
CSS = """<style>
body { font-family: sans-serif; background: #0a0a0a; color: #fff; padding: 10px; }
.card { background: #141414; padding: 15px; border-radius: 12px; margin-bottom: 10px; border: 1px solid #222; }
input, button, select { width: 100%; padding: 12px; margin: 5px 0; border-radius: 8px; border: none; background: #1a1a1a; color: #fff; font-size: 16px; box-sizing: border-box; }
button { background: #ffb300; color: #000; font-weight: bold; cursor: pointer; }
.bar-bg { background: #333; height: 10px; border-radius: 5px; margin: 5px 0; overflow: hidden; }
.bar-fill { background: #ffb300; height: 100%; }
.low { background: #ef4444 !important; }
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

# --- PÁGINA INICIAL ---
@app.get("/", response_class=HTMLResponse)
async def home():
    return f"{CSS}<div class='card'><h2>SABEDORIA</h2><input type='text' id='c' placeholder='CHAVE DA LOJA'><button onclick='location.href=\"/registrar?c=\"+document.getElementById(\"c\").value.toUpperCase()'>ENTRAR</button></div>"

# --- CAIXA (VENDA) ---
@app.get("/registrar", response_class=HTMLResponse)
async def registrar(c: str):
    db = await get_db()
    l = await db.fetchrow("SELECT id, nome FROM lojas WHERE chave_trabalhador = $1 AND pago = TRUE", c.strip().upper())
    if not l: return "❌ LOJA NÃO ENCONTRADA"
    return f"{CSS}<div class='card'><h2>{l['nome']}</h2><form action='/vender' method='post'><input type='hidden' name='c' value='{c}'><input name='p' placeholder='Produto (ex: Arroz ou Categoria)' required><input type='number' name='pr' step='0.1' placeholder='Preço de Venda' required><input type='number' name='q' value='1' placeholder='Quantidade'><button>VENDER</button></form><button style='background:#222;color:#fff' onclick='location.href=\"/dashboard?c={c}\"'>VER STOCK</button></div>"

@app.post("/vender")
async def vender(c:str=Form(...), p:str=Form(...), pr:float=Form(...), q:float=Form(...)):
    db = await get_db()
    async with db.acquire() as conn:
        l = await conn.fetchrow("SELECT id FROM lojas WHERE chave_trabalhador = $1", c.strip().upper())
        await conn.execute("UPDATE stock SET quantidade = quantidade - $1 WHERE loja_id=$2 AND produto=$3", q, l['id'], p.upper())
        await conn.execute("INSERT INTO vendas_live (loja_id, produto, quantidade, preco) VALUES ($1,$2,$3,$4)", l['id'], p.upper(), q, pr)
    return RedirectResponse(f"/registrar?c={c}", status_code=303)

# --- DASHBOARD (INVENTÁRIO) ---
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(c: str):
    db = await get_db()
    l = await db.fetchrow("SELECT id, nome FROM lojas WHERE chave_trabalhador = $1", c.strip().upper())
    estoque = await db.fetch("SELECT produto, quantidade FROM stock WHERE loja_id=$1 ORDER BY quantidade ASC", l['id'])
    html = f"{CSS}<div class='card'><h2>📊 Stock: {l['nome']}</h2>"
    for p in estoque:
        perc = min(100, max(0, p['quantidade'] * 10)) # Barra de exemplo
        html += f"<div>{p['produto']}: {int(p['quantidade'])} un<div class='bar-bg'><div class='bar-fill {'low' if p['quantidade']<5 else ''}' style='width:{perc}%'></div></div></div>"
    return html + "<button onclick='history.back()'>VOLTAR</button></div>"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
