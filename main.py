import os, asyncio, csv, io
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse
import asyncpg
from datetime import datetime

app = FastAPI()
DATABASE_URL = os.getenv("DATABASE_URL")
SUPER_CHAVE = os.getenv("ADMIN_PASSWORD", "$Venicius2005$") 
db_pool = None

@app.on_event("startup")
async def startup():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS lojas (id SERIAL PRIMARY KEY, nome TEXT, gmail_dono TEXT UNIQUE, senha_master TEXT, chave_operador TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS vendas_live (id SERIAL PRIMARY KEY, loja_id INTEGER REFERENCES lojas(id), produto TEXT, quantidade INTEGER, preco DECIMAL, data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        """)

@app.get("/setup_sistema", response_class=HTMLResponse)
async def setup_page():
    return """<body style="font-family:sans-serif;padding:20px;"><form action="/setup_sistema" method="post"><h2>🛠 Criador</h2><input type="password" name="sk" placeholder="Chave Mestre"><input type="text" name="n" placeholder="Nome Loja"><input type="email" name="g" placeholder="Gmail"><input type="text" name="s" placeholder="Senha Master"><input type="text" name="c" placeholder="Chave Op"><button>CRIAR 🚀</button></form></body>"""

@app.post("/setup_sistema")
async def criar_loja(sk:str=Form(...), n:str=Form(...), g:str=Form(...), s:str=Form(...), c:str=Form(...)):
    if sk != SUPER_CHAVE: return "Erro: Chave Mestre Errada!"
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("INSERT INTO lojas (nome, gmail_dono, senha_master, chave_operador) VALUES ($1,$2,$3,$4)", n, g, s, c)
        return "Loja Criada! <a href='/'>Ir para Vendas</a>"
    except: return "Erro: Gmail ou Chave já existem!"

@app.get("/", response_class=HTMLResponse)
async def home():
    return """<body style="font-family:sans-serif;text-align:center;padding:20px;"><h2>AutoReport 📦</h2><form action="/venda" method="post"><input type="text" name="c" placeholder="Chave da Loja"><br><input type="text" name="p" placeholder="Produto"><br><input type="number" name="q" placeholder="Qtd"><br><input type="number" step="0.01" name="pr" placeholder="Preço"><br><button style="background:blue;color:white;padding:10px;">REGISTAR ✅</button></form></body>"""

@app.post("/venda")
async def registrar(c:str=Form(...), p:str=Form(...), q:int=Form(...), pr:float=Form(...)):
    async with db_pool.acquire() as conn:
        l = await conn.fetchrow("SELECT id FROM lojas WHERE chave_operador=$1", c)
        if not l: return "Chave Errada!"
        await conn.execute("INSERT INTO vendas_live (loja_id, produto, quantidade, preco) VALUES ($1,$2,$3,$4)", l['id'], p, q, pr)
    return "✅ OK! <a href='/'>Voltar</a>"

@app.get("/admin", response_class=HTMLResponse)
async def admin():
    return """<form action="/admin/dash" method="post" style="padding:20px;"><h3>Painel Dono</h3><input type="email" name="g" placeholder="Gmail"><br><input type="password" name="s" placeholder="Senha"><br><button>Entrar</button></form>"""

@app.post("/admin/dash", response_class=HTMLResponse)
async def dash(g:str=Form(...), s:str=Form(...)):
    async with db_pool.acquire() as conn:
        loja = await conn.fetchrow("SELECT id, nome FROM lojas WHERE gmail_dono=$1 AND senha_master=$2", g, s)
        if not loja: return "Login Errado!"
        vendas = await conn.fetch("SELECT data_venda, produto, quantidade, preco FROM vendas_live WHERE loja_id=$1 ORDER BY data_venda DESC", loja['id'])
    res = "".join([f"<tr><td>{v['produto']}</td><td>{float(v['quantidade'])*float(v['preco']):.2f} MT</td></tr>" for v in vendas])
    return f"<h3>{loja['nome']}</h3><table border='1'>{res}</table><form action='/admin/export' method='post'><input type='hidden' name='id' value='{loja['id']}'><button>BAIXAR EXCEL</button></form>"

@app.post("/admin/export")
async def export(id:int=Form(...)):
    async with db_pool.acquire() as conn:
        vendas = await conn.fetch("SELECT data_venda, produto, quantidade, preco FROM vendas_live WHERE loja_id=$1", id)
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Data', 'Produto', 'Qtd', 'Preco', 'Total'])
    for v in vendas:
        cw.writerow([v['data_venda'].strftime('%d/%m/%Y'), v['produto'], v['quantidade'], v['preco'], float(v['quantidade'])*float(v['preco'])])
    return StreamingResponse(io.BytesIO(si.getvalue().encode()), media_type="text/csv", headers={"Content-Disposition": "attachment;filename=vendas.csv"})
 
