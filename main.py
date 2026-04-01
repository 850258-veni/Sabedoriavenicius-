import os, io, csv, bcrypt
from datetime import datetime
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from passlib.context import CryptContext
import asyncpg

app = FastAPI()

# Configuração de Segurança
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Configuração do Banco de Dados
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

pool = None

async def get_db():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(DATABASE_URL)
    return pool

# --- PÁGINA DE REGISTO DE VENDAS (INICIAL) ---
@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <body style="font-family:sans-serif; text-align:center; padding:20px; background:#f4f4f4;">
        <div style="max-width:400px; margin:auto; background:white; padding:30px; border-radius:15px; box-shadow:0 4px 15px rgba(0,0,0,0.1);">
            <h2 style="color:#333;">AutoReport Business 📦</h2>
            <form action="/registrar_venda" method="post" style="text-align:left;">
                <label>Chave do Trabalhador:</label><br>
                <input name="c" type="password" required style="width:100%; padding:12px; margin:8px 0; border:1px solid #ccc; border-radius:5px;"><br>
                <label>Produto:</label><br>
                <input name="p" type="text" required style="width:100%; padding:12px; margin:8px 0; border:1px solid #ccc; border-radius:5px;"><br>
                <label>Quantidade:</label><br>
                <input name="q" type="number" step="0.01" required style="width:100%; padding:12px; margin:8px 0; border:1px solid #ccc; border-radius:5px;"><br>
                <label>Preço Unitário (MT):</label><br>
                <input name="pr" type="number" step="0.01" required style="width:100%; padding:12px; margin:8px 0; border:1px solid #ccc; border-radius:5px;"><br><br>
                <button type="submit" style="width:100%; padding:15px; background:#28a745; color:white; border:none; border-radius:5px; font-weight:bold; cursor:pointer;">REGISTAR VENDA ✅</button>
            </form>
        </div>
    </body>
    """

@app.post("/registrar_venda")
async def registrar(c:str=Form(...), p:str=Form(...), q:float=Form(...), pr:float=Form(...)):
    db = await get_db()
    loja = await db.fetchrow("SELECT id FROM lojas WHERE chave_trabalhador=$1", c.strip())
    if not loja: return "❌ Chave da Loja Inválida!"
    
    await db.execute("INSERT INTO vendas_live (loja_id, produto, quantidade, preco) VALUES ($1, $2, $3, $4)",
                     loja['id'], p, q, pr)
    return "✅ Venda Registada com Sucesso! <a href='/'>Voltar</a>"

# --- CRIADOR DE LOJAS (SETUP) ---
@app.get("/setup_sistema", response_class=HTMLResponse)
async def setup_view():
    return """
    <body style="font-family:sans-serif; text-align:center; padding:20px;">
        <h2>🛠️ Criador de Lojas Profissional</h2>
        <form action="/setup_sistema" method="post" style="display:inline-block; text-align:left; background:#eee; padding:20px; border-radius:10px;">
            Chave Mestre:<br><input name="mestre" type="password" required><br>
            Nome da Loja:<br><input name="nome" type="text" required><br>
            Gmail do Dono:<br><input name="gmail" type="email" required><br>
            Senha do Dono:<br><input name="senha" type="password" required><br>
            Chave do Trabalhador:<br><input name="chave_t" type="text" required><br><br>
            <button type="submit" style="background:blue; color:white; padding:12px; width:100%; border:none; border-radius:5px; cursor:pointer;">CRIAR LOJA 🔐</button>
        </form>
    </body>
    """

@app.post("/setup_sistema")
async def setup_action(mestre:str=Form(...), nome:str=Form(...), gmail:str=Form(...), senha:str=Form(...), chave_t:str=Form(...)):
    if mestre != "$Venicius2005$": return "❌ Acesso Negado"
    db = await get_db()
    # Cria tabelas se não existirem
    await db.execute("CREATE TABLE IF NOT EXISTS lojas (id SERIAL PRIMARY KEY, nome TEXT, gmail_dono TEXT UNIQUE, senha_hash TEXT, chave_trabalhador TEXT UNIQUE)")
    await db.execute("CREATE TABLE IF NOT EXISTS vendas_live (id SERIAL PRIMARY KEY, loja_id INTEGER REFERENCES lojas(id), produto TEXT, quantidade FLOAT, preco FLOAT, data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    
    hash_senha = pwd_context.hash(senha)
    try:
        await db.execute("INSERT INTO lojas (nome, gmail_dono, senha_hash, chave_trabalhador) VALUES ($1, $2, $3, $4)",
                         nome, gmail.lower().strip(), hash_senha, chave_t.strip())
        return "✅ Loja Criada com Sucesso! <a href='/admin'>Ir para Login</a>"
    except:
        return "❌ Erro: Gmail ou Chave já existem no banco."

# --- PAINEL ADMINISTRATIVO COM GRÁFICO ---
@app.get("/admin", response_class=HTMLResponse)
async def admin_login():
    return """
    <body style="font-family:sans-serif; text-align:center; padding:50px; background:#f4f4f4;">
        <div style="max-width:350px; margin:auto; background:white; padding:30px; border-radius:10px;">
            <h2>🔐 Login do Dono</h2>
            <form action="/admin/dash" method="post">
                Gmail:<br><input name="g" type="email" required style="width:100%; padding:10px; margin:10px 0;"><br>
                Senha:<br><input name="s" type="password" required style="width:100%; padding:10px; margin:10px 0;"><br><br>
                <button type="submit" style="width:100%; padding:12px; background:black; color:white; border:none; border-radius:5px; cursor:pointer;">ENTRAR NO PAINEL</button>
            </form>
        </div>
    </body>
    """

@app.post("/admin/dash", response_class=HTMLResponse)
async def dash(g:str=Form(...), s:str=Form(...)):
    db = await get_db()
    loja = await db.fetchrow("SELECT * FROM lojas WHERE LOWER(gmail_dono)=LOWER($1)", g.strip())
    if not loja or not pwd_context.verify(s, loja['senha_hash']): return "❌ Login ou Senha Incorretos!"
    
    vendas = await db.fetch("SELECT data_venda, produto, quantidade, preco FROM vendas_live WHERE loja_id=$1 ORDER BY data_venda ASC", loja['id'])
    
    # Dados do Gráfico (Últimas 12 vendas)
    labels = [v['data_venda'].strftime('%H:%M') for v in vendas][-12:]
    valores = [float(v['quantidade'] * v['preco']) for v in vendas][-12:]
    
    total_dia = sum(float(v['quantidade'] * v['preco']) for v in vendas)
    tabela = "".join([f"<tr><td style='padding:10px; border-bottom:1px solid #eee;'>{v['data_venda'].strftime('%d/%m %H:%M')}</td><td>{v['produto']}</td><td style='color:green; font-weight:bold;'>{(v['quantidade']*v['preco']):.2f} MT</td></tr>" for v in reversed(vendas)])

    return f"""
    <head><script src="https://cdn.jsdelivr.net/npm/chart.js"></script></head>
    <body style="font-family:sans-serif; padding:20px; background:#f4f4f4;">
        <div style="max-width:800px; margin:auto; background:white; padding:20px; border-radius:10px; box-shadow:0 2px 5px rgba(0,0,0,0.1);">
            <h2 style="margin-bottom:5px;">📊 Dashboard: {loja['nome']}</h2>
            <h3 style="color:#28a745; margin-top:0;">Faturamento Total: {total_dia:.2f} MT</h3>
            
            <div style="height:300px; margin-bottom:30px;"><canvas id="graficoVendas"></canvas></div>
            
            <form action="/admin/export" method="post" style="margin-bottom:20px;">
                <input type="hidden" name="id" value="{loja['id']}">
                <button type="submit" style="background:#007bff; color:white; border:none; padding:15px; width:100%; border-radius:5px; font-weight:bold; cursor:pointer;">📥 BAIXAR EXCEL ORGANIZADO (CSV)</button>
            </form>

            <table style="width:100%; border-collapse:collapse; text-align:left;">
                <tr style="background:#eee;"><th style="padding:10px;">Data/Hora</th><th>Produto</th><th>Subtotal</th></tr>
                {tabela}
            </table>
        </div>
        <script>
            new Chart(document.getElementById('graficoVendas'), {{
                type: 'line',
                data: {{
                    labels: {labels},
                    datasets: [{{ label: 'Vendas Recentes (MT)', data: {valores}, borderColor: '#007bff', tension: 0.3, fill: true, backgroundColor: 'rgba(0,123,255,0.1)' }}]
                }},
                options: {{ maintainAspectRatio: false }}
            }});
        </script>
    </body>
    """

# --- EXPORTAÇÃO CORRIGIDA (O PULO DO GATO) ---
@app.post("/admin/export")
async def export(id:int=Form(...)):
    db = await get_db()
    vendas = await db.fetch("SELECT data_venda, produto, quantidade, preco FROM vendas_live WHERE loja_id=$1 ORDER BY data_venda DESC", id)
    
    si = io.StringIO()
    # 🐈 PULO DO GATO 1: Força o Excel a reconhecer o separador ponto-e-vírgula
    si.write("sep=;\n")
    
    cw = csv.writer(si, delimiter=';') 
    cw.writerow(['Data', 'Produto', 'Quantidade', 'Preco Unitario', 'Total Ganho'])
    
    for v in vendas:
        total = float(v['quantidade']) * float(v['preco'])
        cw.writerow([
            v['data_venda'].strftime('%d/%m/%Y %H:%M'), 
            v['produto'], 
            str(v['quantidade']).replace('.', ','), # 🐈 PULO DO GATO 2: Troca ponto por vírgula para somas no Excel
            str(v['preco']).replace('.', ','), 
            str(total).replace('.', ',')
        ])
    
    # PULO DO GATO 3: UTF-8 com BOM para os acentos não estragarem
    conteudo = "\ufeff" + si.getvalue()
    return StreamingResponse(
        io.BytesIO(conteudo.encode("utf-8-sig")), 
        media_type="text/csv", 
        headers={"Content-Disposition": f"attachment;filename=Vendas_AutoReport_{datetime.now().strftime('%d_%m')}.csv"}
    )
