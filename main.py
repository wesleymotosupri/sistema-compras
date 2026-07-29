import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.database import init_db
from app.routes import pedido, precos, vinculos
from app.routes import registro_pedidos as pedidos_route

app = FastAPI()

# ── LOGIN ──────────────────────────────────────────────────────
LOGIN_USUARIO = os.getenv("LOGIN_USUARIO", "motosupri")
LOGIN_SENHA   = os.getenv("LOGIN_SENHA", "moto123")
SECRET_KEY    = os.getenv("SESSION_SECRET_KEY", "troque-esta-chave-em-producao")

PUBLIC_PATHS = {"/login"}

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in PUBLIC_PATHS or path.startswith("/static"):
            return await call_next(request)
        if not request.session.get("logged_in"):
            if path.startswith("/api"):
                return JSONResponse({"erro": "Não autenticado"}, status_code=401)
            return RedirectResponse(url="/login")
        return await call_next(request)

# Ordem importa: o último adicionado roda primeiro.
# SessionMiddleware precisa rodar ANTES do AuthMiddleware (pra ter request.session pronto).
app.add_middleware(AuthMiddleware)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)


LOGIN_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Login - Compras Moto Supri</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet"/>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Inter',sans-serif;background:#f4f6f9;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px}}
  .wrap{{display:flex;width:760px;max-width:100%;min-height:460px;border-radius:10px;overflow:hidden;box-shadow:0 12px 40px rgba(0,0,0,.12)}}
  .side{{flex:1;background:linear-gradient(160deg,#222d32 0%,#1a2226 100%);color:#fff;padding:44px 38px;display:flex;flex-direction:column;justify-content:space-between;position:relative;overflow:hidden}}
  .side::before{{content:'';position:absolute;width:280px;height:280px;background:radial-gradient(circle,rgba(0,166,90,.18) 0%,transparent 70%);top:-80px;right:-80px}}
  .side::after{{content:'';position:absolute;width:220px;height:220px;background:radial-gradient(circle,rgba(0,166,90,.12) 0%,transparent 70%);bottom:-60px;left:-60px}}
  .side .brand{{position:relative;z-index:1}}
  .side .brand .icon{{font-size:30px;margin-bottom:14px;display:block}}
  .side .brand h1{{font-size:22px;font-weight:700;letter-spacing:.2px}}
  .side .brand .sub{{font-size:13px;color:#8aa4af;margin-top:4px}}
  .side .foot{{position:relative;z-index:1;font-size:11px;color:#5f7681;line-height:1.6}}
  .side .foot strong{{color:#8aa4af}}
  .form-side{{flex:1;background:#fff;padding:48px 42px;display:flex;flex-direction:column;justify-content:center}}
  .form-side h2{{font-size:19px;font-weight:600;color:#222d32;margin-bottom:6px}}
  .form-side .lead{{font-size:13px;color:#6c757d;margin-bottom:28px}}
  label{{display:block;font-size:11px;font-weight:600;color:#6c757d;text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px}}
  .field{{margin-bottom:18px}}
  input{{width:100%;padding:11px 13px;border:1px solid #dee2e6;border-radius:6px;font-size:14px;font-family:'Inter',sans-serif;outline:none;transition:border .15s,box-shadow .15s;background:#fbfcfd}}
  input:focus{{border-color:#00a65a;box-shadow:0 0 0 3px rgba(0,166,90,.12);background:#fff}}
  button{{width:100%;padding:12px;background:#00a65a;color:#fff;border:none;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer;margin-top:6px;transition:background .15s;letter-spacing:.2px}}
  button:hover{{background:#008d4c}}
  .erro{{background:#f8d7da;color:#721c24;font-size:12.5px;padding:10px 12px;border-radius:6px;margin-bottom:18px;border-left:3px solid #dd4b39}}
  @media(max-width:640px){{.wrap{{flex-direction:column;width:380px}}.side{{padding:32px}}}}
</style>
</head>
<body>
  <div class="wrap">
    <div class="side">
      <div class="brand">
        <span class="icon">🛒</span>
        <h1>Compras</h1>
        <div class="sub">Moto Supri</div>
      </div>
      <div class="foot">Sistema interno de<br/><strong>gestão de pedidos e compras</strong></div>
    </div>
    <div class="form-side">
      <form method="post" action="/login">
        <h2>Entrar</h2>
        <div class="lead">Acesse com suas credenciais</div>
        {erro}
        <div class="field">
          <label>Usuário</label>
          <input type="text" name="usuario" autofocus required/>
        </div>
        <div class="field">
          <label>Senha</label>
          <input type="password" name="senha" required/>
        </div>
        <button type="submit">Entrar</button>
      </form>
    </div>
  </div>
</body>
</html>
"""

@app.get("/login")
def login_page():
    return HTMLResponse(LOGIN_HTML.format(erro=""))

@app.post("/login")
def login_submit(request: Request, usuario: str = Form(...), senha: str = Form(...)):
    if usuario.strip().lower() == LOGIN_USUARIO.lower() and senha == LOGIN_SENHA:
        request.session["logged_in"] = True
        return RedirectResponse(url="/", status_code=303)
    erro_html = '<div class="erro">Usuário ou senha incorretos.</div>'
    return HTMLResponse(LOGIN_HTML.format(erro=erro_html), status_code=401)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")

# ── APP ────────────────────────────────────────────────────────
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