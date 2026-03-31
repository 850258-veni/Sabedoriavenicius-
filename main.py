import os, asyncio, csv, io
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
import asyncpg
from datetime import datetime

app = FastAPI()
DATABASE_URL = os.getenv("DATABASE_URL")
# SUA SENHA PARA CRIAR NOVAS LOJAS (Pode mudar no Render Environment)
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
                nome VARCHAR(100), 
                gmail_dono VARCHAR(100) UNIQUE, 
                senha_master VARCHAR(100),
                chave_operador VARCHAR(50) UNIQUE
            );
            CREATE TABLE IF NOT EXISTS vendas_live (
                id SERIAL PRIMARY KEY, 
                loja_id INTEGER REFERENCES lojas(id), 
                produto VARCHAR(255), 
                quantidade INTEGER, 
                preco DECIMAL(10,2), 
                data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

# --- [NOVO] PÁGINA PARA VOCÊ CADASTRAR CLIENTES ---
@app.get("/setup_sistema", response_class=HTMLResponse)
async def setup_page():
    return """
    <body style="font-family:sans-serif; padding:20px; background:#e9ecef;">
        <div style="max-width:400px; margin:auto; background:white; padding:20px; border-radius:10px;">
            <h2>🛠 Criador de Lojas</h2>
            <form action="/setup_sistema" method="post">
                <input type="password" name="super_key" placeholder="Sua Chave Mestre" required style="width:100%; padding:10px; margin:5px;"><br>
                <hr>
                <input type="text" name="nome_loja" placeholder="Nome da Loja do Cliente" required style="width:100%; padding:10px; margin:5px;"><br>
                <input type="email" name="gmail" placeholder="Gmail do Cliente (User ID)" required style="width:100%; padding:10px; margin:5px;"><br>
                <input type="text" name="senha" placeholder="Senha do Painel do Cliente" required style="width:100%; padding:10px; margin:5px;"><br>
                <input type="text" name="chave_op" placeholder="Chave para o Trabalhador" required style="width:100%; padding:10px; margin:5px;"><br>
                <button type="submit" style="width:100%; background:blue; color:white; padding:15px; border:none; border-radius:5px;">CRIAR NOVA LOJA 🚀</button>
            </form>
        </div>
    </body>
    """

@app.post("/setup_sistema")
async def criar_loja(super_key: str = Form(...), nome_loja: str = Form(...), gmail: str = Form(...), senha: str = Form(...), chave_op: str = Form(...)):
    if super_key != SUPER_CHAVE: return "Acesso Negado!"
    async with db_pool.acquire() as conn:
        try:
            await conn.execute("INSERT INTO lojas (nome, gmail_dono, senha_master, chave_operador) VALUES ($1,$2,$3,$4)", nome_loja, gmail, senha, chave_op)
            return f"<h2>Loja '{nome_loja}' criada com sucesso!</h2><a href='/setup_sistema'>Criar outra</a>"
        except:
            return "Erro: Esse Gmail ou Chave já existem no sistema!"

# --- PÁGINA DE VENDAS (OPERAÇÃO) ---
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body style="font-family:sans-serif; background:#f4f4f9; padding:20px; text-align:center;">
        <div style="max-width:400px; margin:auto; background:white; padding:30px; border-radius:15px; border-top:8px solid #0056b3;">
            <h2>AutoReport Business 📦</h2>
            <form action="/venda" method="post">
                <input type="text" name="chave" placeholder="Chave da Loja" required style="width:100%; padding:12px; margin:8px 0; border:1px solid #ddd; border-radius:8px;">
                <input type="text" name="produto" placeholder="O que vendeu?" required style="width:100%; padding:12px; margin:8px 0; border:1px solid #ddd; border-radius:8px;">
                <input type="number" name="qtd" placeholder="Quantidade" required style="width:100%; padding:12px; margin:8px 0; border:1px solid #ddd; border-radius:8px;">
                <input type="number" step="0.01" name="preco" placeholder="Preço (MT)" required style="width:100%; padding:12px; margin:8px 0; border:1px solid #ddd; border-radius:8px;">
                <button type="submit" style="width:100%; background:#0056b3; color:white; padding:15px; border:none; border-radius:8px; font-weight:bold;">REGISTAR ✅</button>
            </form>
        </div>
    </body>
    """

@app.post("/venda")
async def registrar(chave: str = Form(...), produto: str = Form(...), qtd: int = Form(...), preco: float = Form(...)):
    async with db_pool.acquire() as conn:
        loja = await conn.fetchrow("SELECT id, nome FROM lojas WHERE chave_operador=$1", chave)
        if not loja: return "Erro: Chave Inválida."
        await conn.execute("INSERT INTO vendas_live (loja_id, produto, quantidade, preco) VALUES ($1,$2,$3,$4)", loja['id'], produto, qtd, preco)
    return HTMLResponse(f"<h2>✅ Venda na '{loja['nome']}' Ok!</h2><br><a href='/'>Voltar</a>")

# --- LOGIN DO DONO ---
@app.get("/admin", response_class=HTMLResponse)
async def admin_login():
    return """
    <body style="font-family:sans-serif; text-align:center; padding:100px;">
        <div style="max-width:300px; margin:auto; padding:20px; border:1px solid #ddd; border-radius:10px;">
            <h3>Login do Proprietário</h3>
            <form action="/admin/dashboard" method="post">
                <input type="email" name="gmail" placeholder="Seu Gmail Comercial" required style="width:100%; padding:10px; margin:5px;"><br>
                <input type="password" name="senha" placeholder="Sua Senha Master" required style="width:100%; padding:10px; margin:5px;"><br>
                <button type="submit" style="width:100%; padding:10px; background:black; color:white;">Ver Meu Relatório</button>
            </form>
        </div>
    </body>
    """

# --- DASHBOARD DO DONO (FILTRADO) ---
@app.post("/admin/dashboard", response_class=HTMLResponse)
async def dashboard(gmail: str = Form(...), senha: str = Form(...)):
    async with db_pool.acquire() as conn:
        loja = await conn.fetchrow("SELECT id, nome FROM lojas WHERE gmail_dono=$1 AND senha_master=$2", gmail, senha)
        if not loja: return "Gmail ou Senha incorretos."
        
        vendas = await conn.fetch("SELECT data_venda, produto, quantidade, preco FROM vendas_live WHERE loja_id=$1 ORDER BY data_venda DESC", loja['id'])
        total = sum(float(v['quantidade']) * float(v['preco']) for v in vendas)
        
    lista = "".join([f"<tr><td>{v['produto']}</td><td>{float(v['quantidade'])*float(v['preco']):.2f} MT</td></tr>" for v in vendas])
    return f"""
    <div style="font-family:sans-serif; padding:20px;">
        <h3>📊 Gestão: {loja['nome']}</h3>
        <div style="background:#d4edda; padding:15px; border-radius:10px;"><b>TOTAL EM CAIXA: {total:.2f} MT</b></div>
        <table border="1" style="width:100%; border-collapse:collapse; margin-top:15px;">
            <tr style="background:#eee;"><th>Produto</th><th>Valor Total</th></tr>{lista}
        </table><br>
        <form action="/admin/exportar" method="post">
            <input type="hidden" name="loja_id" value="{loja['id']}">
            <button type="submit" style="background:#28a745; color:white; padding:15px; border:none; border-radius:10px; cursor:pointer;">📥 DESCARREGAR EXCEL</button>
        </form>
    </div>
    """

# --- EXPORTAR EXCEL ---
@app.post("/admin/exportar")
async def exportar(loja_id: int = Form(...)):
    async with db_pool.acquire() as conn:
        vendas = await conn.fetch("SELECT data_venda, produto, quantidade, preco FROM vendas_live WHERE loja_id=$1 ORDER BY data_venda DESC", loja_id)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Data', 'Produto', 'Qtd', 'Preco', 'Total'])
    for v in vendas:
        sub = float(v['quantidade']) * float(v['preco'])
        writer.writerow([v['data_venda'].strftime('%d/%m/%Y'), v['produto'], v['quantidade'], f"{float(v['preco']):.2f}", f"{sub:.2f}"])
    output.seek(0)
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8")), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=loja_{loja_id}.csv"})
 
