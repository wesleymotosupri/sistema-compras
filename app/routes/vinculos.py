from fastapi import APIRouter, HTTPException, UploadFile, File
from sqlalchemy import text
from app.database import engine
import pandas as pd
import io

router = APIRouter()

# ── Fornecedores ──────────────────────────────────────────────
@router.get("/fornecedores")
def listar_fornecedores():
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT nome FROM fornecedores ORDER BY nome")).fetchall()
    return [r[0] for r in rows]

# ── Vínculos ──────────────────────────────────────────────────
@router.get("/vinculos")
def listar_vinculos(busca: str = "", fornecedor: str = ""):
    query = """
        SELECT v.id, v.meu_codigo, p.descricao, v.fornecedor, v.codigo_fornecedor
        FROM vinculos v
        LEFT JOIN meus_produtos p ON p.codigo = v.meu_codigo
        WHERE 1=1
    """
    params = {}
    if busca:
        query += " AND (v.meu_codigo ILIKE :busca OR p.descricao ILIKE :busca)"
        params["busca"] = f"%{busca}%"
    if fornecedor:
        query += " AND v.fornecedor = :fornecedor"
        params["fornecedor"] = fornecedor
    query += " ORDER BY v.meu_codigo, v.fornecedor"
    with engine.connect() as conn:
        rows = conn.execute(text(query), params).fetchall()
    return [dict(r._mapping) for r in rows]

@router.post("/vinculos")
def criar_vinculo(body: dict):
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO meus_produtos (codigo, descricao)
            VALUES (:codigo, :descricao)
            ON CONFLICT (codigo) DO NOTHING
        """), {"codigo": body["meu_codigo"], "descricao": body.get("descricao", "")})
        conn.execute(text("""
            INSERT INTO vinculos (meu_codigo, fornecedor, codigo_fornecedor)
            VALUES (:meu_codigo, :fornecedor, :codigo_fornecedor)
            ON CONFLICT (meu_codigo, fornecedor, codigo_fornecedor) DO NOTHING
        """), body)
        conn.commit()
    return {"ok": True}

@router.delete("/vinculos/{id}")
def deletar_vinculo(id: int):
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM vinculos WHERE id = :id"), {"id": id})
        conn.commit()
    return {"ok": True}

# ── Busca produto por código (autocomplete) ───────────────────
@router.get("/produtos/busca")
def buscar_produto(q: str = ""):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT codigo, descricao FROM meus_produtos
            WHERE codigo ILIKE :q OR descricao ILIKE :q
            LIMIT 10
        """), {"q": f"%{q}%"}).fetchall()
    return [dict(r._mapping) for r in rows]

# ── Importar vínculos via CSV (carga inicial) ─────────────────
@router.post("/vinculos/importar-csv")
async def importar_csv(file: UploadFile = File(...)):
    content = await file.read()
    df = pd.read_csv(io.BytesIO(content), dtype=str)
    df = df.dropna(subset=["meu_codigo", "fornecedor", "codigo_fornecedor"])

    produtos_inseridos = 0
    vinculos_inseridos = 0
    ignorados = 0

    with engine.connect() as conn:
        for _, row in df.iterrows():
            r = conn.execute(text("""
                INSERT INTO meus_produtos (codigo, descricao)
                VALUES (:codigo, :descricao)
                ON CONFLICT (codigo) DO NOTHING
            """), {"codigo": row["meu_codigo"], "descricao": row.get("descricao", "")})
            produtos_inseridos += r.rowcount

            r2 = conn.execute(text("""
                INSERT INTO vinculos (meu_codigo, fornecedor, codigo_fornecedor)
                VALUES (:meu_codigo, :fornecedor, :codigo_fornecedor)
                ON CONFLICT (meu_codigo, fornecedor, codigo_fornecedor) DO NOTHING
            """), {
                "meu_codigo": row["meu_codigo"],
                "fornecedor": row["fornecedor"],
                "codigo_fornecedor": row["codigo_fornecedor"]
            })
            if r2.rowcount == 0:
                ignorados += 1
            else:
                vinculos_inseridos += 1
        conn.commit()

    return {
        "produtos_inseridos": produtos_inseridos,
        "vinculos_inseridos": vinculos_inseridos,
        "ignorados": ignorados
    }