from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.database import init_db
from app.routes import vinculos, precos, pedido

app = FastAPI(title="Sistema de Compras")

@app.on_event("startup")
def startup():
    init_db()

app.include_router(vinculos.router, prefix="/api")
app.include_router(precos.router, prefix="/api")
app.include_router(pedido.router, prefix="/api")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
def index():
    return FileResponse("app/templates/index.html")