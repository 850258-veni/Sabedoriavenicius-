import os, asyncio, csv, io
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
import asyncpg
from datetime import datetime
from passlib.context import CryptContext

# Configuração de Segurança para Senhas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI()
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
                quantidade INTEGER, 
                preco DECIMAL, 
                data_venda TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

# --- SEGURANÇA: FUNÇÕES DE SENHA ---
def hash_senha(senha): return pwd_context.hash(senha)
def verificar_senha(senha, hash): return pwd_context.verify(senha, hash)

# --- SISTEMA DE SETUP ---
@app.post("/setup_sistema")
async def criar_loja(sk:str=Form(...), n:str=Form(...), g:str=Form(...), s:str=Form(...), c:str=Form(...)):
    if sk != SUPER_CHAVE: return "Acesso Negado!"
    pool = await get_db()
    try:
        senha_segura = hash_senha(s)
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO lojas (nome, gmail_dono, senha_hash, chave_operador) VALUES ($1,$2,$3,$4)", 
                               n, g.lower().strip(), senha_segura, c.lower().strip())
        return "Loja Criada com Segurança! <a href='/'>Ir para Vendas</a>"
    except Exception as e:
        return f"Erro: Dados já existentes ou falha no banco."

# --- LOGIN SEGURO DO DONO ---
@app.post("/admin/dash", response_class=HTMLResponse)
async def dash(g:str=Form(...), s:str=Form(...)):
    pool = await get_db()
    async with pool.acquire() as conn:
        loja = await conn.fetchrow("SELECT * FROM lojas WHERE gmail_dono=$1", g.lower().strip())
        if not loja or not verificar_senha(s, loja['senha_hash']):
            return "Login ou Senha Incorretos!"
        
        vendas = await conn.fetch("SELECT * FROM vendas_live WHERE loja_id=$1 ORDER BY data_venda DESC", loja['id'])
    
    # Resto do código do Dash (Total e Tabela) igual ao anterior...
    return "Painel Seguro Acessado" # Simplificado para o exemplo
