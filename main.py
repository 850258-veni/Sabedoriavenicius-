import os, asyncio, uuid, csv, io
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
import asyncpg
from datetime import datetime

app = FastAPI()
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Tete2026")
db_pool = None

@app.on_event("startup")
async def startup():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS lojas (id SERIAL PRIMARY KEY, nome VARCHAR(100), slug VARCHAR(50) UNIQUE);
            CREATE TABLE IF NOT EXISTS usuarios (id SERIAL PRIMARY KEY, loja_id INTEGER, nome VARCHAR(100), api_key VARCHAR(100) UNIQUE, nivel VARCHAR(20));
            CREATE TABLE IF NOT EXISTS vendas_live (id SERIAL PRIMARY KEY, loja_id INTEGER, usuario_id INTEGER, produto VARCHAR(255), quantidade INTEGER, preco DECIMAL(10,2), fechada BOOLEAN DEFAULT FALSE, data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        """)
        # CRIA O USUÁRIO DE TESTE AUTOMATICAMENTE
        await conn.execute("INSERT INTO lojas (nome, slug) VALUES ('Loja Tete', 'piloto') ON CONFLICT DO NOTHING")
        await conn.execute("INSERT INTO usuarios (loja_id, nome, api_key, nivel) VALUES (1, 'Venicius', 'vn-pro-tenant', 'admin') ON CONFLICT DO NOTHING")

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <body style="font-family:sans-serif; padding:20px; background:#f4f4f4;">
        <div style="background:white; padding:20px; border-radius:10px; max-width:400px; margin:auto;">
            <h2>AutoReport Pro 📦</h2>
            <form action="/venda" method="post">
                <input type="password" name="api_key" placeholder="Chave do Operador" required style="width:100%; padding:10px; margin-bottom:10px;">
                <input type="text" name="produto" placeholder="Produto" required style="width:100%; padding:10px; margin-bottom:10px;">
                <input type="number" name="quantidade" placeholder="Qtd" required style="width:100%; padding:10px; margin-bottom:10px;">
                <input type="number" step="0.01" name="preco" placeholder="Preço (MT)" required style="width:100%; padding:10px; margin-bottom:10px;">
                <button type="submit" style="width:100%; background:#0056b3; color:white; padding:15px; border:none; border-radius:5px;">REGISTAR VENDA</button>
            </form>
        </div>
    </body>
    """

@app.post("/venda", response_class=HTMLResponse)
async def registrar_venda(api_key: str = Form(...), produto: str = Form(...), quantidade: int = Form(...), preco: float = Form(...)):
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id, loja_id FROM usuarios WHERE api_key=$1", api_key)
        if not user: return "<h3>Erro: Chave Inválida. Use: vn-pro-tenant</h3>"
        await conn.execute("INSERT INTO vendas_live (loja_id, usuario_id, produto, quantidade, preco) VALUES ($1,$2,$3,$4,$5)", user['loja_id'], user['id'], produto, quantidade, preco)
    return "<h2>✅ Venda Ok!</h2><a href='/'>Voltar</a>"

@app.get("/admin", response_class=HTMLResponse)
async def admin_login():
    return '<form action="/admin/dashboard" method="post"><input type="password" name="pwd"><button>Entrar no Painel</button></form>'

@app.post("/admin/dashboard", response_class=HTMLResponse)
async def dashboard(pwd: str = Form(...)):
    if pwd != ADMIN_PASSWORD: return "Senha errada"
    async with db_pool.acquire() as conn:
        vendas = await conn.fetch("SELECT v.produto, (v.quantidade*v.preco) as total FROM vendas_live v")
    return f"<h3>Total de Vendas: {len(vendas)}</h3><a href='/'>Sair</a>"
