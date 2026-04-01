import os, io, bcrypt, pandas as pd
from datetime import datetime
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from passlib.context import CryptContext
import asyncpg

app = FastAPI()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
DATABASE_URL = os.getenv("DATABASE_URL").replace("postgres://", "postgresql://", 1) if os.getenv("DATABASE_URL") else None
pool = None

async def get_db():
    global pool
    if pool is None: pool = await asyncpg.create_pool(DATABASE_URL)
    return pool

# ESTILO VISUAL PROFISSIONAL
CSS = """
<style>
    :root { --bg: #0f172a; --card: #1e293b; --text: #f8fafc; --primary: #3b82f6; --success: #10b981; }
    body { font-family: sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 20px; display: flex; justify-content: center; }
    .container { width: 100%; max-width: 500px; background: var(--card); padding: 30px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.3); }
    input { width: 100%; padding: 12px; margin: 10px 0; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: white; box-sizing: border-box; }
    button { width: 100%; padding: 15px; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; transition: 0.3s; width: 100%; }
    .btn-reg { background: var(--success); color: white; }
    .btn-adm { background: var(--primary); color: white; }
    table { width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 14px; }
    th { background: #334155; padding: 12px; text-align: left; }
    td { padding: 12px; border-bottom: 1px solid #334155; }
</style>
"""

@app.get("/", response_class=HTMLResponse)
async def index():
    return f"{CSS}<div class='container'><h2>🛒 AutoReport Business</h2><form action='/registrar_venda' method='post'><label>Chave do Trabalhador</label><input name='c' type='password' required><label>Produto</label><input name='p' type='text' required><label>Quantidade</label><input name='q' type='number' step='0.01' value='1'><label>Preço (MT)</label><input name='pr' type='number' step='0.01' required><br><br><button type='submit' class='btn-reg'>REGISTAR VENDA ✅</button></form></div>"

@app.post("/registrar_venda")
async def registrar(c:str=Form(...), p:str=Form(...), q:float=Form(...), pr:float=Form(...)):
    db = await get_db()
    loja = await db.fetchrow("SELECT id FROM lojas WHERE chave_trabalhador=$1", c.strip())
    if not loja: return "❌ Chave Inválida"
    await db.execute("INSERT INTO vendas_live (loja_id, produto, quantidade, preco) VALUES ($1, $2, $3, $4)", loja['id'], p, q, pr)
    return "✅ Registado! <a href='/' style='color:white;'>Voltar</a>"

@app.get("/admin", response_class=HTMLResponse)
async def admin_view():
    return f"{CSS}<div class='container'><h2>🔐 Painel do Dono</h2><form action='/admin/dash' method='post'><input name='g' type='email' placeholder='Gmail' required><input name='s' type='password' placeholder='Senha' required><br><br><button type='submit' class='btn-adm'>ENTRAR</button></form></div>"

@app.post("/admin/dash", response_class=HTMLResponse)
async def dash(g:str=Form(...), s:str=Form(...)):
    db = await get_db()
    loja = await db.fetchrow("SELECT * FROM lojas WHERE LOWER(gmail_dono)=LOWER($1)", g.strip())
    if not loja or not pwd_context.verify(s, loja['senha_hash']): return "❌ Acesso Negado"
    vendas = await db.fetch("SELECT data_venda, produto, quantidade, preco FROM vendas_live WHERE loja_id=$1 ORDER BY data_venda DESC", loja['id'])
    
    total = sum(v['quantidade'] * v['preco'] for v in vendas)
    linhas = "".join([f"<tr><td>{v['data_venda'].strftime('%H:%M')}</td><td>{v['produto']}</td><td>{v['quantidade']*v['preco']:.2f} MT</td></tr>" for v in vendas])

    return f"{CSS}<div class='container' style='max-width:800px;'><h2>📊 {loja['nome']}</h2><h1 style='color:var(--success);'>{total:.2f} MT</h1><form action='/admin/export' method='post'><input type='hidden' name='id' value='{loja['id']}'><button type='submit' style='background:#334155; color:white;'>📥 DESCARREGAR EXCEL PERFEITO</button></form><table><thead><tr><th>Hora</th><th>Produto</th><th>Total</th></tr></thead><tbody>{linhas}</tbody></table></div>"

@app.post("/admin/export")
async def export(id:int=Form(...)):
    db = await get_db()
    vendas = await db.fetch("SELECT data_venda, produto, quantidade, preco FROM vendas_live WHERE loja_id=$1 ORDER BY data_venda DESC", id)
    df = pd.DataFrame(vendas, columns=['data_venda', 'produto', 'quantidade', 'preco'])
    df['Soma Total'] = df['quantidade'] * df['preco']
    df.columns = ['Data/Hora', 'Produto', 'Qtd', 'Preço Unitário', 'Soma Total']
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Relatório')
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                             headers={"Content-Disposition": f"attachment; filename=Relatorio_AutoReport.xlsx"})

@app.get("/setup_sistema", response_class=HTMLResponse)
async def setup_v(): 
    return f"{CSS}<div class='container'><form action='/setup_sistema' method='post'><h2>🏗️ Criar Loja</h2><input name='mestre' placeholder='Chave Mestre' type='password'><input name='nome' placeholder='Nome da Loja'><input name='gmail' placeholder='Gmail'><input name='senha' placeholder='Senha' type='password'><input name='chave_t' placeholder='Chave Trabalhador'><button type='submit' class='btn-adm'>CRIAR</button></form></div>"

@app.post("/setup_sistema")
async def setup_a(mestre:str=Form(...), nome:str=Form(...), gmail:str=Form(...), senha:str=Form(...), chave_t:str=Form(...)):
    if mestre != "$Venicius2005$": return "Negado"
    db = await get_db()
    await db.execute("CREATE TABLE IF NOT EXISTS lojas (id SERIAL PRIMARY KEY, nome TEXT, gmail_dono TEXT UNIQUE, senha_hash TEXT, chave_trabalhador TEXT UNIQUE)")
    await db.execute("CREATE TABLE IF NOT EXISTS vendas_live (id SERIAL PRIMARY KEY, loja_id INTEGER REFERENCES lojas(id), produto TEXT, quantidade FLOAT, preco FLOAT, data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    await db.execute("INSERT INTO lojas (nome, gmail_dono, senha_hash, chave_trabalhador) VALUES ($1, $2, $3, $4)", nome, gmail.lower().strip(), pwd_context.hash(senha), chave_t.strip())
    return "✅ Loja Criada!"
 
