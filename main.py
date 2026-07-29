from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.requests import Request
from app.database import init_db
from app.routes import pedido, precos, vinculos
from app.routes import registro_pedidos as pedidos_route

app = FastAPI()

@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
def index():
    with open("app/templates/index.html", "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(content=content)

app.include_router(pedido.router, prefix="/api")
app.include_router(precos.router, prefix="/api")
app.include_router(vinculos.router, prefix="/api")
app.include_router(pedidos_route.router, prefix="/api")