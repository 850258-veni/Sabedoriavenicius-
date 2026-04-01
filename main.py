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

# --- DESIGN PREMIUM GRAPHITE & GOLD ---
CSS = """
<style>
    :root { 
        --bg: #121212; 
        --card: #1e1e1e; 
        --text: #e0e0e0; 
        --primary: #ffb300; 
        --accent: #333333;
    }
    body { 
        font-family: 'Segoe UI', Roboto, sans-serif; 
        background: var(--bg); 
        color: var(--text); 
        margin: 0; padding: 20px; 
        display: flex; justify-content: center; 
    }
    .container { 
        width: 100%; max-width: 450px; 
        background: var(--card); 
        padding: 40px; border-radius: 12px; 
        border: 1px solid #2c2c2c;
        box-shadow: 0 20px 40px rgba(0,0,0,0.5); 
    }
    h2 { color: var(--primary); text-transform: uppercase; letter-spacing: 2px; font-size: 1.5rem; text-align: center; }
    input { 
        width: 100%; padding: 14px; margin: 12px 0; 
        border-radius: 4px; border: 1px solid #444; 
        background: #252525; color: white; box-sizing: border-box; 
    }
    button { 
        width: 100%; padding: 16px; border: none; border-radius: 4px; 
        font-weight: bold; cursor: pointer; transition: 0.3s; 
        text-transform: uppercase; letter-spacing: 1px;
    }
    .btn-reg { background: var(--primary); color: #000; }
    .btn-adm { background: #e0e0e0; color: #000; }
    button:hover { filter: brightness(1.2); transform: translateY(-2px); }
    table { width: 100%; border-collapse: collapse; margin-top: 25px; }
    th { border-bottom: 2px solid var(--primary); padding: 12px; text-align: left; color: var(--primary); font-size: 12px; }
    td { padding: 12px; border-bottom: 1px solid #2c2c2c; font-size: 14px; }
    .total-box { font-size: 40px; color: white; text-align: center; margin: 20px 0; font-weight: 200; }
</style>
"""

@app.get("/", response_class=HTMLResponse)
async def index():
    return f"{CSS}<div class='container'><h2>AutoReport</h2><p style='text-align:center; color:#888;'>Registo de Operações</p><form action='/registrar_venda' method='post'><input name='c' type='password' placeholder='CHAVE DO POSTO' required><input name='p' type='text' placeholder='NOME DO PRODUTO' required><input name='q' type='number' step='0.01' placeholder='QUANTIDADE' value='1'><input name='pr' type='number' step='0.01' placeholder='PREÇO UNITÁRIO (MT)' required><br><br><button type='submit' class='btn-reg'>EFETUAR REGISTO</button></form></div>"

@app.post("/registrar_venda")
async def registrar(c:str=Form(...), p:str=Form(...), q:float=Form(...), pr:float=Form(...)):
    db = await get_db()
    loja = await db.fetchrow("SELECT id FROM lojas WHERE chave_trabalhador=$1", c.strip())
    if not loja: return "❌ ERRO: CHAVE INVÁLIDA"
    await db.execute("INSERT INTO vendas_live (loja_id, produto, quantidade, preco) VALUES ($1, $2, $3, $4)", loja['id'], p, q, pr)
    return "✅ SUCESSO! <a href='/' style='color:var(--primary); text-decoration:none;'>[ VOLTAR ]</a>"

@app.get("/admin", response_class=HTMLResponse)
async def admin_view():
    return f"{CSS}<div class='container'><h2>ADMINISTRAÇÃO</h2><form action='/admin/dash' method='post'><input name='g' type='email' placeholder='GMAIL CORPORATIVO' required><input name='s' type='password' placeholder='SENHA DE ACESSO' required><br><br><button type='submit' class='btn-adm'>ACEDER AO PAINEL</button></form></div>"

@app.post("/admin/dash", response_class=HTMLResponse)
async def dash(g:str=Form(...), s:str=Form(...)):
    db = await get_db()
    loja = await db.fetchrow("SELECT * FROM lojas WHERE LOWER(gmail_dono)=LOWER($1)", g.strip())
    if not loja or not pwd_context.verify(s, loja['senha_hash']): return "❌ ACESSO NEGADO"
    vendas = await db.fetch("SELECT data_venda, produto, quantidade, preco FROM vendas_live WHERE loja_id=$1 ORDER BY data_venda DESC", loja['id'])
    
    total = sum(v['quantidade'] * v['preco'] for v in vendas)
    linhas = "".join([f"<tr><td>{v['data_venda'].strftime('%H:%M')}</td><td>{v['produto']}</td><td>{v['quantidade']*v['preco']:.2f} MT</td></tr>" for v in vendas])

    return f"{CSS}<div class='container' style='max-width:800px;'><h2>{loja['nome']}</h2><div class='total-box'>{total:.2f} <span style='font-size:18px;'>MT</span></div><form action='/admin/export' method='post'><input type='hidden' name='id' value='{loja['id']}'><button type='submit' style='background:#333; color:white; border:1px solid #555;'>EXPORTAR RELATÓRIO PROFISSIONAL</button></form><table><thead><tr><th>HORA</th><th>ITEM</th><th>VALOR TOTAL</th></tr></thead><tbody>{linhas}</tbody></table></div>"

@app.post("/admin/export")
async def export(id:int=Form(...)):
    db = await get_db()
    vendas = await db.fetch("SELECT data_venda, produto, quantidade, preco FROM vendas_live WHERE loja_id=$1 ORDER BY data_venda DESC", id)
    df = pd.DataFrame(vendas, columns=['data_venda', 'produto', 'quantidade', 'preco'])
    df['Soma Total'] = df['quantidade'] * df['preco']
    df['data_venda'] = df['data_venda'].dt.strftime('%d/%m/%Y %H:%M')
    df.columns = ['Data e Hora', 'Produto', 'Qtd', 'Preço Unitário', 'Soma Total']
    
    output = io.BytesIO()
    # Usando xlsxwriter para auto-ajustar as colunas (Adeus #####)
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Vendas')
        worksheet = writer.sheets['Vendas']
        for i, col in enumerate(df.columns):
            column_len = max(df[col].astype(str).str.len().max(), len(col)) + 2
            worksheet.set_column(i, i, column_len)
            
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                             headers={"Content-Disposition": f"attachment; filename=AutoReport_Relatorio.xlsx"})

@app.get("/setup_sistema", response_class=HTMLResponse)
async def setup_v(): 
    return f"{CSS}<div class='container'><h2>CONFIGURAÇÃO</h2><form action='/setup_sistema' method='post'><input name='mestre' placeholder='MASTER KEY' type='password'><input name='nome' placeholder='NOME DA LOJA'><input name='gmail' placeholder='GMAIL DONO'><input name='senha' placeholder='PASSWORD DONO' type='password'><input name='chave_t' placeholder='CHAVE DO TRABALHADOR'><br><br><button type='submit' class='btn-reg'>CRIAR UNIDADE</button></form></div>"

@app.post("/setup_sistema")
async def setup_a(mestre:str=Form(...), nome:str=Form(...), gmail:str=Form(...), senha:str=Form(...), chave_t:str=Form(...)):
    if mestre != "$Venicius2005$": return "NEGADO"
    db = await get_db()
    await db.execute("CREATE TABLE IF NOT EXISTS lojas (id SERIAL PRIMARY KEY, nome TEXT, gmail_dono TEXT UNIQUE, senha_hash TEXT, chave_trabalhador TEXT UNIQUE)")
    await db.execute("CREATE TABLE IF NOT EXISTS vendas_live (id SERIAL PRIMARY KEY, loja_id INTEGER REFERENCES lojas(id), produto TEXT, quantidade FLOAT, preco FLOAT, data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    await db.execute("INSERT INTO lojas (nome, gmail_dono, senha_hash, chave_trabalhador) VALUES ($1, $2, $3, $4)", nome, gmail.lower().strip(), pwd_context.hash(senha), chave_t.strip())
    return "✅ UNIDADE CRIADA!"
