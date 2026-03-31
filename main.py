import os, asyncio, uuid, csv, io
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
import asyncpg
from datetime import datetime

app = FastAPI()

# CONFIGURAÇÕES DE AMBIENTE (Configure no Render > Environment)
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Tete2026")

db_pool = None

@app.on_event("startup")
async def startup():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        # 1. CRIAÇÃO DO BANCO AUTOMÁTICA
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS lojas (
                id SERIAL PRIMARY KEY, nome VARCHAR(100) NOT NULL, slug VARCHAR(50) UNIQUE NOT NULL, ativo BOOLEAN DEFAULT TRUE
            );
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY, loja_id INTEGER REFERENCES lojas(id) ON DELETE CASCADE,
                nome VARCHAR(100) NOT NULL, api_key VARCHAR(100) UNIQUE NOT NULL, nivel VARCHAR(20) DEFAULT 'operador', ativo BOOLEAN DEFAULT TRUE
            );
            CREATE TABLE IF NOT EXISTS vendas_live (
                id SERIAL PRIMARY KEY, uuid_venda UUID DEFAULT gen_random_uuid() UNIQUE,
                loja_id INTEGER REFERENCES lojas(id) ON DELETE CASCADE, usuario_id INTEGER REFERENCES usuarios(id),
                produto VARCHAR(255) NOT NULL, quantidade INTEGER NOT NULL, preco DECIMAL(10, 2) NOT NULL, 
                data_venda TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, fechada BOOLEAN DEFAULT FALSE
            );
            CREATE TABLE IF NOT EXISTS fecho_caixa (
                id SERIAL PRIMARY KEY, loja_id INTEGER REFERENCES lojas(id) ON DELETE CASCADE,
                usuario_id INTEGER REFERENCES usuarios(id), valor_sistema DECIMAL(10, 2) NOT NULL,
                valor_contado DECIMAL(10, 2) NOT NULL, diferenca DECIMAL(10, 2) NOT NULL, data_fecho TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # Setup da Loja Piloto para o seu teste em Tete
        loja_id = await conn.fetchval("INSERT INTO lojas (nome, slug) VALUES ('Loja Piloto Tete', 'piloto') ON CONFLICT (slug) DO UPDATE SET nome=EXCLUDED.nome RETURNING id")
        await conn.execute("INSERT INTO usuarios (loja_id, nome, api_key, nivel) VALUES ($1, 'Venicius Master', 'vn-pro-tenant', 'admin') ON CONFLICT (api_key) DO NOTHING", loja_id)

# --- INTERFACE DE VENDA (O QUE O FUNCIONÁRIO VÊ) ---
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1">
    <style>body{font-family:sans-serif; background:#f4f7f6; display:flex; justify-content:center; padding:20px;}
    .card{background:white; padding:25px; border-radius:15px; width:100%; max-width:400px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-top:8px solid #0056b3;}
    input{width:100%; padding:12px; margin:10px 0; border:1px solid #ddd; border-radius:8px;}
    button{width:100%; background:#0056b3; color:white; border:none; padding:15px; border-radius:8px; font-weight:bold; cursor:pointer;}
    </style></head>
    <body><div class="card"><h2>AutoReport Pro 📦</h2><form action="/venda" method="post">
    <input type="password" name="api_key" placeholder="Chave do Operador" required>
    <input type="text" name="produto" placeholder="Produto" required>
    <input type="number" name="quantidade" placeholder="Qtd" required min="1">
    <input type="number" step="0.01" name="preco" placeholder="Preço (MT)" required min="0.01">
    <button type="submit">REGISTAR VENDA</button></form></div></body></html>
    """

@app.post("/venda", response_class=HTMLResponse)
async def registrar_venda(api_key: str = Form(...), produto: str = Form(...), quantidade: int = Form(...), preco: float = Form(...)):
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id, loja_id FROM usuarios WHERE api_key=$1 AND ativo=TRUE", api_key)
        if not user: return "<h3>Erro: Chave Inválida.</h3>"
        row = await conn.fetchrow("INSERT INTO vendas_live (loja_id, usuario_id, produto, quantidade, preco) VALUES ($1,$2,$3,$4,$5) RETURNING uuid_venda", user['loja_id'], user['id'], produto, quantidade, preco)
    return f"<div style='text-align:center; padding:40px; font-family:sans-serif;'><h2>✅ Venda Ok!</h2><p>ID: {row['uuid_venda']}</p><a href='/'>Voltar</a></div>"

# --- PAINEL DO DONO (GESTÃO, FECHO E EXCEL) ---
@app.post("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(pwd: str = Form(...), slug: str = Form("piloto")):
    if pwd != ADMIN_PASSWORD: return "<h3>Senha Errada.</h3>"
    async with db_pool.acquire() as conn:
        loja = await conn.fetchrow("SELECT id, nome FROM lojas WHERE slug=$1", slug)
        vendas = await conn.fetch("SELECT v.data_venda, u.nome, v.produto, (v.quantidade*v.preco) as total FROM vendas_live v JOIN usuarios u ON v.usuario_id=u.id WHERE v.loja_id=$1 AND v.fechada=FALSE ORDER BY v.data_venda DESC", loja['id'])
        total_pendente = sum(v['total'] for v in vendas)
    
    rows = "".join([f"<tr><td>{v['nome']}</td><td>{v['produto']}</td><td>{v['total']:.2f} MT</td></tr>" for v in vendas])
    return f"""
    <div style="font-family:sans-serif; padding:20px;">
        <h2>Gestão: {loja['nome']}</h2>
        <div style="background:#e3f2fd; padding:15px; border-radius:10px;"><b>PENDENTE EM CAIXA: {total_pendente:.2f} MT</b></div>
        <hr><table border="1" style="width:100%; border-collapse:collapse;"><tr><th>Vendedor</th><th>Produto</th><th>Total</th></tr>{rows}</table>
        <br>
        <form action="/admin/fecho/executar" method="post">
            <input type="hidden" name="pwd" value="{pwd}"><input type="hidden" name="loja_id" value="{loja['id']}">
            <input type="number" step="0.01" name="valor_contado" placeholder="Valor Real Contado (MT)" required style="padding:10px;">
            <button type="submit" style="background:black; color:white; padding:10px;">FECHAR CAIXA</button>
        </form>
        <form action="/admin/vendas/exportar" method="post" style="margin-top:20px;">
            <input type="hidden" name="pwd" value="{pwd}"><input type="hidden" name="slug" value="{slug}">
            <button type="submit" style="background:#ff9800; color:white; padding:10px; border:none; border-radius:8px; cursor:pointer;">EXPORTAR PARA EXCEL (CSV)</button>
        </form>
    </div>
    """

# --- ROTA DE EXPORTAÇÃO ---
@app.post("/admin/vendas/exportar")
async def exportar_vendas(pwd: str = Form(...), slug: str = Form(...)):
    if pwd != ADMIN_PASSWORD: raise HTTPException(status_code=403)
    async with db_pool.acquire() as conn:
        loja = await conn.fetchrow("SELECT id FROM lojas WHERE slug=$1", slug)
        vendas = await conn.fetch("SELECT v.data_venda, u.nome, v.produto, v.quantidade, v.preco, (v.quantidade*v.preco) as total FROM vendas_live v JOIN usuarios u ON v.usuario_id=u.id WHERE v.loja_id=$1 ORDER BY v.data_venda DESC", loja['id'])
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Data', 'Vendedor', 'Produto', 'Qtd', 'Preco', 'Total'])
    for v in vendas: writer.writerow([v['data_venda'].strftime('%d/%m/%Y %H:%M'), v['nome'], v['produto'], v['quantidade'], v['preco'], v['total']])
    
    output.seek(0)
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8")), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=vendas_{slug}.csv"})

# --- ROTA DE FECHO ---
@app.post("/admin/fecho/executar", response_class=HTMLResponse)
async def fecho_exec(pwd: str = Form(...), loja_id: int = Form(...), valor_contado: float = Form(...)):
    if pwd != ADMIN_PASSWORD: return "Erro."
    async with db_pool.acquire() as conn:
        total_sistema = await conn.fetchval("SELECT SUM(quantidade * preco) FROM vendas_live WHERE loja_id=$1 AND fechada=FALSE", loja_id) or 0
        diferenca = valor_contado - float(total_sistema)
        await conn.execute("INSERT INTO fecho_caixa (loja_id, valor_sistema, valor_contado, diferenca) VALUES ($1,$2,$3,$4)", loja_id, total_sistema, valor_contado, diferenca)
        await conn.execute("UPDATE vendas_live SET fechada=TRUE WHERE loja_id=$1 AND fechada=FALSE", loja_id)
    cor = "green" if diferenca == 0 else "red"
    return f"<div style='text-align:center; padding:50px;'><h1 style='color:{cor};'>DIFERENÇA: {diferenca:.2f} MT</h1><a href='/'>Voltar</a></div>"
