import os
import logging
import traceback
import asyncpg
import httpx
import urllib.parse
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# --- Configurações das Variáveis de Ambiente ---
# Para o WhatsApp (CallMeBot)
WHATSAPP_PHONE = os.getenv("WHATSAPP_PHONE")
WHATSAPP_API_KEY = os.getenv("WHATSAPP_API_KEY")

# Para o Banco de Dados (PostgreSQL no Render/Koyeb)
DB_URL = os.getenv("DATABASE_URL")

app = FastAPI(title="AutoReport Pro - WhatsApp Edition")
logger = logging.getLogger("uvicorn.error")
db_pool = None

# --- Inicialização do Banco de Dados ---
@app.on_event("startup")
async def startup():
    global db_pool
    db_pool = await asyncpg.create_pool(dsn=DB_URL, min_size=5, max_size=20)

@app.on_event("shutdown")
async def shutdown():
    if db_pool:
        await db_pool.close()

# --- Função de Alerta via WhatsApp ---
async def alert_whatsapp(message: str):
    if WHATSAPP_PHONE and WHATSAPP_API_KEY:
        encoded_message = urllib.parse.quote(message)
        url = f"https://api.callmebot.com/whatsapp.php?phone={WHATSAPP_PHONE}&text={encoded_message}&apikey={WHATSAPP_API_KEY}"
        
        async with httpx.AsyncClient() as client:
            try:
                # Timeout curto para não travar a API se o CallMeBot estiver lento
                response = await client.get(url, timeout=10.0)
                if response.status_code != 200:
                    logger.error(f"Erro CallMeBot: {response.text}")
            except Exception as e:
                logger.error(f"Falha ao conectar com WhatsApp API: {e}")

# --- Schemas de Dados ---
class VendaSchema(BaseModel):
    produto: str
    quantidade: int
    preco: float

# --- Lógica de Segurança (API Key) ---
async def verify_api_key(x_api_key: str):
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id, nome FROM usuarios WHERE api_key=$1", x_api_key)
        if not user:
            raise HTTPException(status_code=403, detail="API Key inválida")
        return user

# --- Rota Principal (Interface do Cliente) ---
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>AutoReport Tete</title>
            <style>
                body { font-family: sans-serif; text-align: center; padding: 20px; background: #f4f4f9; }
                .card { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); max-width: 300px; margin: auto; }
                input { width: 90%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 5px; }
                button { background: #25D366; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; width: 95%; font-weight: bold; }
            </style>
        </head>
        <body>
            <div class="card">
                <h2>AutoReport Pro</h2>
                <p>Registe a Venda Abaixo</p>
                <form action="/v1/venda" method="post">
                    <input type="text" name="x_api_key" placeholder="Sua API Key" required>
                    <input type="text" name="produto" placeholder="Nome do Produto" required>
                    <input type="number" name="quantidade" placeholder="Quantidade" required>
                    <input type="number" step="0.01" name="preco" placeholder="Preço (MT)" required>
                    <button type="submit">REGISTAR E NOTIFICAR</button>
                </form>
            </div>
        </body>
    </html>
    """

# --- Rota de Registo de Venda ---
@app.post("/v1/venda")
async def registrar_venda(venda: VendaSchema, x_api_key: str):
    user = await verify_api_key(x_api_key)
    
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO vendas_live (usuario_id, produto, quantidade, preco) VALUES ($1,$2,$3,$4)",
            user['id'], venda.produto, venda.quantidade, venda.preco
        )
    
    # Criar a mensagem formatada para o WhatsApp
    msg = (
        f"🛍️ *NOVA VENDA: {user['nome']}*\n"
        f"--------------------------\n"
        f"📦 *Produto:* {venda.produto}\n"
        f"🔢 *Qtd:* {venda.quantidade}\n"
        f"💰 *Total:* {venda.preco * venda.quantidade:,.2f} MT\n"
        f"--------------------------\n"
        f"🚀 _Enviado via AutoReport Tete_"
    )
    
    # Enviar alerta em background (não trava a resposta da API)
    import asyncio
    asyncio.create_task(alert_whatsapp(msg))
    
    return {"status": "sucesso", "mensagem": "Venda registada e WhatsApp notificado!"}

# --- Middleware de Erros Críticos ---
@app.middleware("http")
async def capture_exceptions(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Erro crítico: {tb}")
        # Notifica você (desenvolvedor) sobre o erro técnico no WhatsApp
        await alert_whatsapp(f"🚨 *ERRO NO SISTEMA*:\nLocal: {request.url}\nErro: {str(e)[:100]}")
        return JSONResponse(status_code=500, content={"detail": "Erro interno de servidor"})
