import os
import pandas as pd
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from passlib.context import CryptContext
import asyncpg
from datetime import datetime

app = FastAPI()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Configuração da Base de Dados no Render
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
    # 1. Tabela de Lojas
    await db.execute("""
        CREATE TABLE IF NOT EXISTS lojas (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            gmail_dono TEXT UNIQUE NOT NULL,
            senha_hash TEXT NOT NULL,
            chave_trabalhador TEXT UNIQUE NOT NULL,
            pago BOOLEAN DEFAULT FALSE
        );
    """)
    # 2. Tabela de Preços Padrão (Memória de Custo)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS precos_padrao (
            id SERIAL PRIMARY KEY,
            loja_id INT NOT NULL,
            produto TEXT NOT NULL,
            preco_custo FLOAT NOT NULL,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(loja_id, LOWER(produto))
        );
    """)
    # 3. Tabela de Vendas com Coluna de Custo
    await db.execute("""
        CREATE TABLE IF NOT EXISTS vendas_live (
            id SERIAL PRIMARY KEY,
            loja_id INT NOT NULL,
            produto TEXT NOT NULL,
            quantidade FLOAT NOT NULL,
            preco FLOAT NOT NULL,
            preco_custo FLOAT DEFAULT 0,
            data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    print("✅ SISTEMA DE BASE DE DADOS SINCRONIZADO!")

# --- CSS PREMIUM MOBILE-FIRST ---
CSS = """
<style>
    :root { --bg: #0a0a0a; --card: #141414; --primary: #ffb300; --success: #10b981; --danger: #ef4444; }
    body { font-family: 'Segoe UI', sans-serif; background: var(--bg); color: #fff; margin: 0; padding: 15px; }
    .card { background: var(--card); padding: 20px; border-radius: 12px; border: 1px solid #222; margin-bottom: 15px; }
    input, button { width: 100%; padding: 12px; margin: 8px 0; border-radius: 8px; border: 1px solid #333; font-size: 16px; }
    input { background: #1a1a1a; color: #fff; }
    button { background: var(--primary); color: #000; font-weight: bold; cursor: pointer; border: none; }
    .trend-up { border-left: 5px solid var(--success); }
    .trend-down { border-left: 5px solid var(--danger); }
    .trend-stable { border-left: 5px solid var(--primary); }
    table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 14px; }
    th, td { text-align: left; padding: 10px; border-bottom: 1px solid #222; }
    th { color: var(--primary); font-size: 11px; text-transform: uppercase; }
</style>
"""

# --- ROTA: FORMULÁRIO DE REGISTO INTELIGENTE ---
@app.get("/registrar", response_class=HTMLResponse)
async def pagina_registo(c: str, p: str = None):
    db = await get_db()
    loja = await db.fetchrow("SELECT id FROM lojas WHERE chave_trabalhador=$1", c.strip())
    if not loja: return "❌ ACESSO NEGADO"

    custo_sugerido = 0.0
    if p:
        custo_sugerido = await db.fetchval(
            "SELECT preco_custo FROM precos_padrao WHERE loja_id=$1 AND LOWER(produto)=LOWER($2)",
            loja['id'], p.strip()
        ) or 0.0

    return f"""
    <head><meta name="viewport" content="width=device-width, initial-scale=1">{CSS}</head>
    <div class="card">
        <h3>Registar Venda</h3>
        <form action="/registrar_venda" method="post">
            <input type="hidden" name="c" value="{c}">
            <label>Produto:</label>
            <input type="text" name="p" value="{p or ''}" placeholder="Nome do Produto" required 
                   onblur="if(this.value) window.location.href='/registrar?c={c}&p='+this.value">
            
            <label>Quantidade:</label>
            <input type="number" name="q" value="1" step="0.01" required>

            <label>Preço de Venda (Cada):</label>
            <input type="number" name="pr" step="0.1" required>

            <label style="color: var(--primary);">Custo Unitário (Auto):</label>
            <input type="number" name="pc" value="{custo_sugerido}" step="0.1" required>

            <button type="submit">CONFIRMAR VENDA</button>
        </form>
    </div>
    """

# --- ROTA: PROCESSAR VENDA E MEMORIZAR CUSTO ---
@app.post("/registrar_venda")
async def registrar_venda(c:str=Form(...), p:str=Form(...), q:float=Form(...), pr:float=Form(...), pc:float=Form(...)):
    db = await get_db()
    loja = await db.fetchrow("SELECT id FROM lojas WHERE chave_trabalhador=$1", c.strip())
    if not loja: return "❌ ERRO"

    # 1. Salva a venda
    await db.execute(
        "INSERT INTO vendas_live (loja_id, produto, quantidade, preco, preco_custo) VALUES ($1, $2, $3, $4, $5)",
        loja['id'], p, q, pr, pc
    )
    # 2. Atualiza memória de custo
    await db.execute("""
        INSERT INTO precos_padrao (loja_id, produto, preco_custo) VALUES ($1, $2, $3)
        ON CONFLICT (loja_id, LOWER(produto)) DO UPDATE SET preco_custo = EXCLUDED.preco_custo
    """, loja['id'], p, pc)
    
    return RedirectResponse(url=f"/registrar?c={c}", status_code=303)

# --- ROTA: DASHBOARD DE LUCRO E TENDÊNCIA ---
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(c:str):
    db = await get_db()
    loja = await db.fetchrow("SELECT id, nome FROM lojas WHERE chave_trabalhador=$1", c.strip())
    if not loja: return "❌ ACESSO NEGADO"

    rows = await db.fetch("SELECT produto, quantidade, preco, preco_custo, data_venda FROM vendas_live WHERE loja_id=$1", loja['id'])
    if not rows: return f"{CSS}<div class='card'>Nenhuma venda registada.</div>"

    df = pd.DataFrame([dict(r) for r in rows])
    df['lucro'] = (df['preco'] - df['preco_custo']) * df['quantidade']
    df['data'] = pd.to_datetime(df['data_venda']).dt.date

    # Tendência
    lucro_diario = df.groupby('data')['lucro'].sum().sort_index().reset_index()
    estilo_trend, msg_trend, alerta = "trend-stable", "📊 TENDÊNCIA: Estável", "Dados em análise."
    
    if len(lucro_diario) > 1:
        hoje = lucro_diario.iloc[-1]['lucro']
        media = lucro_diario['lucro'].tail(4).iloc[:-1].mean()
        var = ((hoje - media)/media*100) if media != 0 else 0
        if var > 5: estilo_trend, msg_trend, alerta = "trend-up", "📈 LUCRO A SUBIR", "Excelente performance!"
        elif var < -5: estilo_trend, msg_trend, alerta = "trend-down", "📉 LUCRO EM QUEDA", "Atenção aos custos e margens!"

    # Resumo
    resumo = df.groupby('produto').agg({'quantidade':'sum', 'lucro':'sum'}).reset_index()
    top_p = resumo.loc[resumo['lucro'].idxmax()]

    html_tabela = "".join([f"<tr><td>{r['produto']}</td><td>{r['quantidade']:.0f}</td><td style='color:var(--success)'>{r['lucro']:.2f}</td></tr>" for _, r in resumo.iterrows()])

    return f"""
    <head><meta name="viewport" content="width=device-width, initial-scale=1">{CSS}</head>
    <div class="card {estilo_trend}">
        <div style="font-size:12px; font-weight:bold; color:#aaa;">{msg_trend}</div>
        <h2 style="margin:5px 0;">{loja['nome']}</h2>
        <p style="font-size:13px; color:#888;">{alerta}</p>
    </div>
    
    <div class="card">
        <span style="font-size:11px; color:var(--primary);">PRODUTO ESTRELA</span><br>
        <b style="font-size:20px;">{top_p['produto']}</b><br>
        <span style="color:var(--success);">+{top_p['lucro']:.2f} MT Lucro Líquido</span>
    </div>

    <div class="card">
        <h3>Performance de Itens</h3>
        <table>
            <thead><tr><th>ITEM</th><th>QTD</th><th>LUCRO (MT)</th></tr></thead>
            <tbody>{html_tabela}</tbody>
        </table>
    </div>
    """
