from fastapi import APIRouter, UploadFile, File
from sqlalchemy import text
from app.database import engine
import pandas as pd
import io
import base64

router = APIRouter()

@router.post("/precos/preview")
async def preview_excel(file: UploadFile = File(...)):
    content = await file.read()
    xl = pd.ExcelFile(io.BytesIO(content))
    abas = xl.sheet_names
    preview = {}
    for aba in abas:
        df = pd.read_excel(xl, sheet_name=aba, nrows=15, header=None)
        df = df.fillna("")
        df = df.astype(str)
        colunas = [f"Col {i+1}" for i in range(len(df.columns))]
        preview[aba] = {"colunas": colunas, "linhas": df.values.tolist()}
    file_b64 = base64.b64encode(content).decode()
    return {"abas": abas, "preview": preview, "file_b64": file_b64}

@router.post("/precos/importar-json")
async def importar_precos_json(body: dict):
    fornecedor    = body.get("fornecedor", "")
    aba           = body.get("aba", "")
    coluna_codigo = body.get("coluna_codigo", "")
    coluna_preco  = body.get("coluna_preco", "")
    file_b64      = body.get("file_b64", "")

    print(f"DEBUG JSON: fornecedor={fornecedor} aba={aba} col_codigo={coluna_codigo} col_preco={coluna_preco}")

    if not file_b64:
        return {"erro": "Arquivo não enviado"}

    try:
        content   = base64.b64decode(file_b64)
        col_idx   = int(coluna_codigo.replace("Col ", "").strip()) - 1
        preco_idx = int(coluna_preco.replace("Col ", "").strip()) - 1
    except Exception as e:
        return {"erro": f"Erro: {e}"}

    # Tenta a aba selecionada, se não achar usa a primeira
    try:
        df = pd.read_excel(io.BytesIO(content), sheet_name=aba if aba else 0, header=None)
    except Exception:
        df = pd.read_excel(io.BytesIO(content), sheet_name=0, header=None)

    df = df.fillna("")
    df = df.astype(str)

    df_sel = df.iloc[:, [col_idx, preco_idx]].copy()
    df_sel.columns = ["codigo_fornecedor", "preco"]
    df_sel["codigo_fornecedor"] = df_sel["codigo_fornecedor"].astype(str).str.strip()
    df_sel["preco"] = pd.to_numeric(df_sel["preco"], errors="coerce")
    df_sel = df_sel[df_sel["codigo_fornecedor"] != ""]
    df_sel = df_sel[df_sel["codigo_fornecedor"] != "nan"]
    df_sel = df_sel.dropna(subset=["preco"])
    df_sel = df_sel[df_sel["preco"] > 0]
    df_sel = df_sel.drop_duplicates(subset=["codigo_fornecedor"], keep="last")

    print(f"DEBUG JSON: total_valido={len(df_sel)}")

    if df_sel.empty:
        return {"fornecedor": fornecedor, "atualizados": 0}

    codigos = df_sel["codigo_fornecedor"].tolist()
    precos  = df_sel["preco"].tolist()

    with engine.connect() as conn:
        raw    = conn.connection
        cursor = raw.cursor()

        buf = io.StringIO()
        for c, p in zip(codigos, precos):
            buf.write(f"{fornecedor}\t{c}\t{p}\n")
        buf.seek(0)

        cursor.execute("CREATE TEMP TABLE tmp_precos (fornecedor text, codigo_fornecedor text, preco numeric) ON COMMIT DROP")
        cursor.copy_from(buf, 'tmp_precos', columns=('fornecedor', 'codigo_fornecedor', 'preco'))
        cursor.execute("""
            INSERT INTO precos (fornecedor, codigo_fornecedor, preco, atualizado_em)
            SELECT fornecedor, codigo_fornecedor, preco, NOW() FROM tmp_precos
            ON CONFLICT (fornecedor, codigo_fornecedor)
            DO UPDATE SET preco = EXCLUDED.preco, atualizado_em = NOW()
        """)
        raw.commit()

    return {"fornecedor": fornecedor, "atualizados": len(codigos)}

@router.put("/precos/manual")
async def atualizar_preco_manual(body: dict):
    fornecedor        = body.get("fornecedor")
    codigo_fornecedor = body.get("codigo_fornecedor")
    preco             = float(body.get("preco", 0))
    if not fornecedor or not codigo_fornecedor or preco <= 0:
        return {"erro": "Dados inválidos"}
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO precos (fornecedor, codigo_fornecedor, preco, atualizado_em)
            VALUES (:fornecedor, :codigo_fornecedor, :preco, NOW())
            ON CONFLICT (fornecedor, codigo_fornecedor)
            DO UPDATE SET preco = EXCLUDED.preco, atualizado_em = NOW()
        """), {"fornecedor": fornecedor, "codigo_fornecedor": codigo_fornecedor, "preco": preco})
        conn.commit()
    return {"ok": True}

@router.get("/precos/resumo")
def resumo_precos():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT fornecedor, COUNT(*) as total, MAX(atualizado_em) as ultima_atualizacao
            FROM precos GROUP BY fornecedor ORDER BY fornecedor
        """)).fetchall()
    return [dict(r._mapping) for r in rows]

@router.get("/precos/todos")
def todos_precos():
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT fornecedor, codigo_fornecedor, preco FROM precos")).fetchall()
    return [dict(r._mapping) for r in rows]

@router.get("/precos/fornecedor/{fornecedor}")
def precos_por_fornecedor(fornecedor: str, busca: str = ""):
    with engine.connect() as conn:
        query = "SELECT codigo_fornecedor, preco FROM precos WHERE fornecedor = :fornecedor"
        params = {"fornecedor": fornecedor}
        if busca:
            query += " AND codigo_fornecedor ILIKE :busca"
            params["busca"] = f"%{busca}%"
        query += " ORDER BY codigo_fornecedor"
        rows = conn.execute(text(query), params).fetchall()
    return [dict(r._mapping) for r in rows]

@router.delete("/precos/fornecedor-delete/{fornecedor}")
def excluir_precos_fornecedor(fornecedor: str):
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM precos WHERE fornecedor = :fornecedor"), {"fornecedor": fornecedor})
        conn.commit()
    return {"ok": True}

@router.delete("/precos/limpar-todos")
def limpar_todos_precos():
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM precos"))
        conn.commit()
    return {"ok": True}