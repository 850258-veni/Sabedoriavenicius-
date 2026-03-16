import os, traceback
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel
import asyncpg

app = FastAPI()

# Inicializa Pool de Banco de Dados
@app.on_event("startup")
async def startup():
    app.state.db_pool = await asyncpg.create_pool(dsn=os.getenv("DATABASE_URL"), min_size=5, max_size=20)

@app.on_event("shutdown")
async def shutdown():
    await app.state.db_pool.close()

class Venda(BaseModel):
    produto: str
    quantidade: int
    preco: float

@app.post("/v1/venda")
async def registrar(venda: Venda, x_api_key: str = Header(...)):
    async with app.state.db_pool.acquire() as conn:
        u_id = await conn.fetchval("SELECT id FROM usuarios WHERE api_key = $1", x_api_key)
        if not u_id: raise HTTPException(status_code=403, detail="Chave Inválida")
        
        await conn.execute(
            "INSERT INTO vendas_live (usuario_id, produto, quantidade, preco) VALUES ($1, $2, $3, $4)",
            u_id, venda.produto, venda.quantidade, venda.preco
        )
    return {"status": "sucesso"}
