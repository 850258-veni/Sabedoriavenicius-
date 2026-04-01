import os, asyncio, csv, io
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse
import asyncpg
from datetime import datetime

app = FastAPI()
DATABASE_URL = os.getenv("DATABASE_URL")
# Senha mestre padrão para o setup
SUPER_CHAVE = os.getenv("ADMIN_PASSWORD", "$Venicius2005$") 
db_pool = None

@app.on_event("startup")
async def startup():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS lojas (
                id SERIAL PRIMARY KEY, 
                nome TEXT, 
                gmail_dono TEXT UNIQUE, 
                senha_master TEXT, 
                chave_operador TEXT UNIQUE
            );
            CREATE TABLE IF NOT EXISTS vendas_live (
                id SERIAL PRIMARY KEY, 
                loja_id INTEGER REFERENCES lojas(id), 
                produto TEXT, 
                quantidade INTEGER, 
                preco DECIMAL, 
                data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

# --- PÁGINA DE CRIAÇÃO DE LOJAS ---
@app.get("/setup_sistema", response_class=HTMLResponse)
async def setup_page():
    return """<body style="font-family:sans-serif;padding:20px;text-align:center;">
    <h2>🛠 Criador de Lojas Profissional</h2>
    <form action="/setup_sistema" method="post" style="max-width:300px;margin:auto;">
        <input type="password" name="sk" placeholder="Sua Chave Mestre" required style="width:100%;margin:5px;padding:10px;"><br>
        <input type="text" name="n" placeholder="Nome da Loja" required style="width:100%;margin:5px;padding:10px;"><br>
        <input type="email" name="g" placeholder="Gmail do Dono" required style="width:100%;margin:5px;padding:10px;"><br>
        <input type="text" name="s" placeholder="Senha do Dono" required style="width:100%;margin:5px;padding:10px;"><br>
        <input type="text" name="c" placeholder="Chave do Trabalhador" required style="width:100%;margin:5px;padding:10px;"><br>
        <button style="background:blue;color:white;width:100%;padding:15px;border:none;cursor:pointer;">CRIAR LOJA 🚀</button>
    </form></body>"""

@app.post("/setup_sistema")
async def criar_loja(sk:str=Form(...), n:str=Form(...), g:str=Form(...), s:str=Form(...), c:str=Form(...)):
    if sk != SUPER_CHAVE: return "Acesso Negado: Chave Mestre Errada!"
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("INSERT INTO lojas (nome, gmail_dono, senha_master, chave_operador) VALUES ($1,$2,$3,$4)", n, g, s, c)
        return f"Sucesso! Loja '{n}' criada. <a href='/'>Ir para Vendas</a>"
    except: return "Erro: Este Gmail ou Chave de Trabalhador já existem!"

# --- PÁGINA DE VENDAS (TRABALHADOR) ---
@app.get("/", response_class=HTMLResponse)
async def home():
    return """<body style="font-family:sans-serif;text-align:center;padding:20px;">
    <h2>AutoReport Business 📦</h2>
    <form action="/venda" method="post" style="max-width:300px;margin:auto;">
        <input type="text" name="c" placeholder="Chave da Loja" required style="width:100%;margin:5px;padding:10px;"><br>
        <input type="text" name="p" placeholder="Produto" required style="width:100%;margin:5px;padding:10px;"><br>
        <input type="number" name="q" placeholder="Quantidade" required style="width:100%;margin:5px;padding:10px;"><br>
        <input type="number" step="0.01" name="pr" placeholder="Preço Unitário" required style="width:100%;margin:5px;padding:10px;"><br>
        <button style="background:#0056b3;color:white;width:100%;padding:15px;border:none;cursor:pointer;">REGISTAR VENDA ✅</button>
    </form></body>"""

@app.post("/venda")
async def registrar(c:str=Form(...), p:str=Form(...), q:int=Form(...), pr:float=Form(...)):
    async with db_pool.acquire() as conn:
        loja = await conn.fetchrow("SELECT id FROM lojas WHERE chave_operador=$1", c)
        if not loja: return "Erro: Chave da Loja Inválida!"
        await conn.execute("INSERT INTO vendas_live (loja_id, produto, quantidade, preco) VALUES ($1,$2,$3,$4)", loja['id'], p, q, pr)
    return "Venda Registada! <a href='/'>Voltar</a>"

# --- PAINEL DO DONO ---
@app.get("/admin", response_class=HTMLResponse)
async def admin():
    return """<body style="font-family:sans-serif;text-align:center;padding:20px;">
    <form action="/admin/dash" method="post" style="max-width:300px;margin:auto;">
        <h3>Login do Proprietário</h3>
        <input type="email" name="g" placeholder="Seu Gmail" required style="width:100%;margin:5px;padding:10px;"><br>
        <input type="password" name="s" placeholder="Sua Senha" required style="width:100%;margin:5px;padding:10px;"><br>
        <button style="width:100%;padding:15px;background:black;color:white;cursor:pointer;">ENTRAR</button>
    </form></body>"""

@app.post("/admin/dash", response_class=HTMLResponse)
async def dash(g:str=Form(...), s:str=Form(...)):
    async with db_pool.acquire() as conn:
        loja = await conn.fetchrow("SELECT id, nome FROM lojas WHERE gmail_dono=$1 AND senha_master=$2", g, s)
        if not loja: return "Erro: Login ou Senha Incorretos!"
        vendas = await conn.fetch("SELECT data_venda, produto, quantidade, preco FROM vendas_live WHERE loja_id=$1 ORDER BY data_venda DESC", loja['id'])
    
    total_geral = sum(float(v['quantidade']) * float(v['preco']) for v in vendas)
    linhas = "".join([f"<tr><td>{v['data_venda'].strftime('%d/%m %H:%M')}</td><td>{v['produto']}</td><td>{float(v['quantidade'])*float(v['preco']):.2f} MT</td></tr>" for v in vendas])
    
    return f"""<div style="font-family:sans-serif;padding:20px;">
    <h3>Loja: {loja['nome']}</h3>
    <p>Faturamento Total: <b>{total_geral:.2f} MT</b></p>
    <table border="1" style="width:100%;border-collapse:collapse;">
        <tr style="background:#eee;"><th>Data</th><th>Produto</th><th>Total</th></tr>
        {linhas}
    </table><br>
    <form action="/admin/export" method="post">
        <input type="hidden" name="id" value="{loja['id']}">
        <button style="background:green;color:white;padding:15px;border:none;cursor:pointer;">📥 BAIXAR EXCEL (CSV)</button>
    </form></div>"""

@app.post("/admin/export")
async def export(id:int=Form(...)):
    async with db_pool.acquire() as conn:
        vendas = await conn.fetch("SELECT data_venda, produto, quantidade, preco FROM vendas_live WHERE loja_id=$1", id)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['DATA', 'PRODUTO', 'QTD', 'PRECO_UNIT', 'TOTAL_ITEM'])
    for v in vendas:
        total_item = float(v['quantidade']) * float(v['preco'])
        writer.writerow([v['data_venda'].strftime('%d/%m/%Y %H:%M'), v['produto'], v['quantidade'], f"{float(v['preco']):.2f}", f"{total_item:.2f}"])
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv", headers={"Content-Disposition": "attachment;filename=vendas.csv"})
