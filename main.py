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
        await conn.execute("INSERT INTO lojas (nome, slug) VALUES ('Loja Tete', 'piloto') ON CONFLICT DO NOTHING")
        await conn.execute("INSERT INTO usuarios (loja_id, nome, api_key, nivel) VALUES (1, 'Venicius', 'vn-pro-tenant', 'admin') ON CONFLICT DO NOTHING")

# TELA DE VENDAS (DESIGN MELHORADO)
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <head><meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body{font-family:sans-serif; background:#f0f2f5; display:flex; justify-content:center; padding:20px;}
    .card{background:white; padding:25px; border-radius:15px; width:100%; max-width:400px; box-shadow:0 4px 10px rgba(0,0,0,0.1); border-top:8px solid #0056b3;}
    input{width:100%; padding:12px; margin:8px 0; border:1px solid #ddd; border-radius:8px; box-sizing:border-box;}
    button{width:100%; background:#0056b3; color:white; border:none; padding:15px; border-radius:8px; font-weight:bold; cursor:pointer;}
    </style></head>
    <body><div class="card"><h2>AutoReport Business 📦</h2><form action="/venda" method="post">
    <input type="password" name="api_key" placeholder="Chave do Operador" required>
    <input type="text" name="produto" placeholder="Nome do Produto" required>
    <input type="number" name="quantidade" placeholder="Quantidade" required min="1">
    <input type="number" step="0.01" name="preco" placeholder="Preço Unitário (MT)" required min="0.01">
    <button type="submit">REGISTAR VENDA ✅</button></form></div></body>
    """

@app.post("/venda", response_class=HTMLResponse)
async def registrar_venda(api_key: str = Form(...), produto: str = Form(...), quantidade: int = Form(...), preco: float = Form(...)):
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id, loja_id FROM usuarios WHERE api_key=$1", api_key)
        if not user: return "<h3>Erro: Chave Inválida.</h3><a href='/'>Voltar</a>"
        await conn.execute("INSERT INTO vendas_live (loja_id, usuario_id, produto, quantidade, preco) VALUES ($1,$2,$3,$4,$5)", user['loja_id'], user['id'], produto, quantidade, preco)
    return "<div style='text-align:center; padding:50px;'><h2>✅ Venda Registada com Sucesso!</h2><br><a href='/'>Fazer Nova Venda</a></div>"

# LOGIN DO ADMINISTRADOR
@app.get("/admin", response_class=HTMLResponse)
async def admin_login():
    return """
    <body style="font-family:sans-serif; text-align:center; padding:100px;">
        <div style="max-width:300px; margin:auto; padding:20px; border:1px solid #ddd; border-radius:10px;">
            <h3>Painel de Gestão</h3>
            <form action="/admin/dashboard" method="post">
                <input type="password" name="pwd" placeholder="Senha Master" required style="padding:10px; width:100%;"><br><br>
                <button type="submit" style="background:black; color:white; padding:10px; width:100%;">Entrar</button>
            </form>
        </div>
    </body>
    """

# DASHBOARD COM BOTÃO DE EXCEL
@app.post("/admin/dashboard", response_class=HTMLResponse)
async def dashboard(pwd: str = Form(...)):
    if pwd != ADMIN_PASSWORD: return "Senha errada"
    async with db_pool.acquire() as conn:
        vendas = await conn.fetch("SELECT v.data_venda, v.produto, v.quantidade, v.preco, (v.quantidade*v.preco) as total FROM vendas_live v ORDER BY v.data_venda DESC")
        total_geral = sum(v['total'] for v in vendas)
    
    lista_vendas = "".join([f"<tr><td>{v['produto']}</td><td>{v['total']:.2f} MT</td></tr>" for v in vendas])
    return f"""
    <div style="font-family:sans-serif; padding:20px;">
        <h2>📊 Resumo de Vendas - Tete</h2>
        <div style="background:#d4edda; padding:15px; border-radius:10px; margin-bottom:20px;">
            <b>TOTAL ACUMULADO: {total_geral:.2f} MT</b>
        </div>
        <table border="1" style="width:100%; border-collapse:collapse; margin-bottom:20px;">
            <tr style="background:#eee;"><th>Produto</th><th>Valor Total</th></tr>{lista_vendas}
        </table>
        
        <form action="/admin/exportar" method="post">
            <input type="hidden" name="pwd" value="{pwd}">
            <button type="submit" style="background:#28a745; color:white; padding:15px; border:none; border-radius:10px; cursor:pointer; font-weight:bold;">
                📥 DESCARREGAR RELATÓRIO (EXCEL)
            </button>
        </form>
        <br><a href="/">Sair</a>
    </div>
    """

# FUNÇÃO QUE GERA O ARQUIVO EXCEL (CSV)
@app.post("/admin/exportar")
async def exportar_vendas(pwd: str = Form(...)):
    if pwd != ADMIN_PASSWORD: raise HTTPException(status_code=403)
    async with db_pool.acquire() as conn:
        vendas = await conn.fetch("SELECT data_venda, produto, quantidade, preco FROM vendas_live ORDER BY data_venda DESC")
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Data', 'Produto', 'Qtd', 'Preco Unitario', 'Total'])
    for v in vendas:
        total = v['quantidade'] * v['preco']
        writer.writerow([v['data_venda'].strftime('%d/%m/%Y'), v['produto'], v['quantidade'], v['preco'], total])
    
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=relatorio_vendas.csv"}
    )
