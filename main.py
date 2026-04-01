import os, asyncio, csv, io
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse
import asyncpg
from datetime import datetime
from passlib.context import CryptContext

# Configuração de Segurança: Bcrypt para esconder senhas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI()

# Ajuste automático do link do banco de dados para Python
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SUPER_CHAVE = os.getenv("ADMIN_PASSWORD", "$Venicius2005$")
db_pool = None

async def get_db():
    global db_pool
    if not db_pool:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
    return db_pool

@app.on_event("startup")
async def startup():
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS lojas (
                id SERIAL PRIMARY KEY, 
                nome TEXT, 
                gmail_dono TEXT UNIQUE, 
                senha_hash TEXT, 
                chave_operador TEXT UNIQUE
            );
            CREATE TABLE IF NOT EXISTS vendas_live (
                id SERIAL PRIMARY KEY, 
                loja_id INTEGER REFERENCES lojas(id), 
                produto TEXT, 
                quantidade DECIMAL, 
                preco DECIMAL, 
                data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

# --- PÁGINA INICIAL: REGISTO DE VENDAS ---
@app.get("/", response_class=HTMLResponse)
async def home():
    return """<body style="font-family:sans-serif;text-align:center;padding:20px;background:#f4f4f4;">
    <div style="max-width:400px;margin:auto;background:white;padding:20px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.1);">
        <h2>AutoReport Business 📦</h2>
        <form action="/venda" method="post">
            <input type="text" name="c" placeholder="Chave da Loja" required style="width:100%;margin:10px 0;padding:12px;border:1px solid #ccc;border-radius:5px;"><br>
            <input type="text" name="p" placeholder="Produto" required style="width:100%;margin:10px 0;padding:12px;border:1px solid #ccc;border-radius:5px;"><br>
            <input type="number" step="0.01" name="q" placeholder="Quantidade" required style="width:100%;margin:10px 0;padding:12px;border:1px solid #ccc;border-radius:5px;"><br>
            <input type="number" step="0.01" name="pr" placeholder="Preço Unitário (MT)" required style="width:100%;margin:10px 0;padding:12px;border:1px solid #ccc;border-radius:5px;"><br>
            <button style="background:#0056b3;color:white;width:100%;padding:15px;border:none;border-radius:5px;font-weight:bold;cursor:pointer;">REGISTAR VENDA ✅</button>
        </form>
    </div></body>"""

@app.post("/venda")
async def registrar(c:str=Form(...), p:str=Form(...), q:float=Form(...), pr:float=Form(...)):
    pool = await get_db()
    async with pool.acquire() as conn:
        loja = await conn.fetchrow("SELECT id FROM lojas WHERE LOWER(chave_operador)=LOWER($1)", c.strip())
        if not loja: return "Erro: Chave da Loja Inválida!"
        await conn.execute("INSERT INTO vendas_live (loja_id, produto, quantidade, preco) VALUES ($1,$2,$3,$4)", 
                           loja['id'], p, q, pr)
    return "✅ Venda Registada com Sucesso! <a href='/'>Voltar</a>"

# --- PAINEL DO DONO (ADMIN) ---
@app.get("/admin", response_class=HTMLResponse)
async def admin():
    return """<body style="font-family:sans-serif;text-align:center;padding:20px;">
    <div style="max-width:400px;margin:auto;">
        <h3>Acesso do Proprietário</h3>
        <form action="/admin/dash" method="post">
            <input type="email" name="g" placeholder="Seu Gmail" required style="width:100%;margin:10px 0;padding:12px;"><br>
            <input type="password" name="s" placeholder="Sua Senha" required style="width:100%;margin:10px 0;padding:12px;"><br>
            <button style="width:100%;padding:15px;background:black;color:white;border:none;cursor:pointer;">ENTRAR NO PAINEL</button>
        </form>
    </div></body>"""

@app.post("/admin/dash", response_class=HTMLResponse)
async def dash(g:str=Form(...), s:str=Form(...)):
    pool = await get_db()
    async with pool.acquire() as conn:
        loja = await conn.fetchrow("SELECT * FROM lojas WHERE LOWER(gmail_dono)=LOWER($1)", g.strip())
        if not loja or not pwd_context.verify(s, loja['senha_hash']):
            return "❌ Gmail ou Senha Incorretos!"
        
        vendas = await conn.fetch("SELECT data_venda, produto, quantidade, preco FROM vendas_live WHERE loja_id=$1 ORDER BY data_venda DESC", loja['id'])
    
    linhas = ""
    total_dia = 0
    for v in vendas:
        subtotal = float(v['quantidade']) * float(v['preco'])
        total_dia += subtotal
        linhas += f"<tr><td style='padding:8px;'>{v['data_venda'].strftime('%d/%m %H:%M')}</td><td>{v['produto']}</td><td>{v['quantidade']}</td><td>{subtotal:.2f} MT</td></tr>"

    return f"""<body style="font-family:sans-serif;padding:20px;">
        <h2>Gestão: {loja['nome']}</h2>
        <div style="background:#e7f3ff;padding:15px;border-radius:5px;margin-bottom:20px;">
            <strong>Total Acumulado: {total_dia:.2f} MT</strong>
        </div>
        <table border="1" style="width:100%;border-collapse:collapse;text-align:center;">
            <tr style="background:#eee;"><th>Data</th><th>Produto</th><th>Qtd</th><th>Total</th></tr>
            {linhas}
        </table><br>
        <form action="/admin/export" method="post">
            <input type="hidden" name="id" value="{loja['id']}">
            <button style="background:green;color:white;padding:15px;width:100%;border:none;cursor:pointer;">📥 BAIXAR EXCEL (CSV)</button>
        </form>
    </body>"""

# --- SETUP DO SISTEMA (CRIAÇÃO DE LOJAS) ---
@app.get("/setup_sistema", response_class=HTMLResponse)
async def setup_page():
    return """<body style="font-family:sans-serif;padding:20px;text-align:center;">
    <h2>🛠 Criador de Lojas Profissional</h2>
    <form action="/setup_sistema" method="post" style="max-width:300px;margin:auto;">
        <input type="password" name="sk" placeholder="Chave Mestre" required style="width:100%;margin:5px;padding:10px;"><br>
        <input type="text" name="n" placeholder="Nome da Loja" required style="width:100%;margin:5px;padding:10px;"><br>
        <input type="email" name="g" placeholder="Gmail do Dono" required style="width:100%;margin:5px;padding:10px;"><br>
        <input type="text" name="s" placeholder="Senha do Dono" required style="width:100%;margin:5px;padding:10px;"><br>
        <input type="text" name="c" placeholder="Chave do Trabalhador" required style="width:100%;margin:5px;padding:10px;"><br>
        <button style="background:blue;color:white;width:100%;padding:15px;border:none;">CRIAR LOJA COM CRIPTOGRAFIA 🔐</button>
    </form></body>"""

@app.post("/setup_sistema")
async def criar_loja(sk:str=Form(...), n:str=Form(...), g:str=Form(...), s:str=Form(...), c:str=Form(...)):
    if sk != SUPER_CHAVE: return "Chave Mestre Errada!"
    pool = await get_db()
    hash_seguro = pwd_context.hash(s)
    try:
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO lojas (nome, gmail_dono, senha_hash, chave_operador) VALUES ($1,$2,$3,$4)", 
                               n, g.lower().strip(), hash_seguro, c.lower().strip())
        return "✅ Loja Criada com Segurança! As senhas estão criptografadas."
    except:
        return "❌ Erro: Este Gmail ou Chave já existem."

@app.post("/admin/export")
async def export(id:int=Form(...)):
    pool = await get_db()
    async with pool.acquire() as conn:
        vendas = await conn.fetch("SELECT data_venda, produto, quantidade, preco FROM vendas_live WHERE loja_id=$1 ORDER BY data_venda DESC", id)
    
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Data', 'Produto', 'Qtd', 'Preco_Unit', 'Total'])
    for v in vendas:
        total = float(v['quantidade']) * float(v['preco'])
        cw.writerow([v['data_venda'].strftime('%d/%m/%Y %H:%M'), v['produto'], v['quantidade'], v['preco'], total])
    
    return StreamingResponse(io.BytesIO(si.getvalue().encode("utf-8-sig")), 
                             media_type="text/csv", 
                             headers={"Content-Disposition": "attachment;filename=vendas.csv"})
