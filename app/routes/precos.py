from fastapi import APIRouter, UploadFile, File
from sqlalchemy import text
from app.database import engine
import pandas as pd
import io

router = APIRouter()

@router.post("/precos/preview")
async def preview_excel(file: UploadFile = File(...)):
    """Retorna abas e primeiras linhas do Excel para o usuário mapear colunas."""
    content = await file.read()
    xl = pd.ExcelFile(io.BytesIO(content))
    abas = xl.sheet_names
    preview = {}
    for aba in abas:
        df = pd.read_excel(xl, sheet_name=aba, nrows=5, dtype=str)
        preview[aba] = {
            "colunas": df.columns.tolist(),
            "linhas": df.fillna("").values.tolist()
        }
    return {"abas": abas, "preview": preview}

@router.post("/precos/importar")
async def importar_precos(
    file: UploadFile = File(...),
    fornecedor: str = "",
    aba: str = "",
    coluna_codigo: str = "",
    coluna_preco: str = ""
):
    """Importa preços de um Excel já mapeado."""
    content = await file.read()
    df = pd.read_excel(io.BytesIO(content), sheet_name=aba, dtype=str)

    if coluna_codigo not in df.columns or coluna_preco not in df.columns:
        return {"erro": "Colunas não encontradas no arquivo"}

    df = df[[coluna_codigo, coluna_preco]].dropna()
    df.columns = ["codigo_fornecedor", "preco"]
    df["codigo_fornecedor"] = df["codigo_fornecedor"].str.strip()
    df["preco"] = pd.to_numeric(df["preco"].str.replace(",", "."), errors="coerce")
    df = df.dropna(subset=["preco"])
    df = df[df["preco"] > 0]

    atualizados = 0
    with engine.connect() as conn:
        for _, row in df.iterrows():
            r = conn.execute(text("""
                INSERT INTO precos (fornecedor, codigo_fornecedor, preco, atualizado_em)
                VALUES (:fornecedor, :codigo_fornecedor, :preco, NOW())
                ON CONFLICT (fornecedor, codigo_fornecedor)
                DO UPDATE SET preco = EXCLUDED.preco, atualizado_em = NOW()
            """), {
                "fornecedor": fornecedor,
                "codigo_fornecedor": row["codigo_fornecedor"],
                "preco": float(row["preco"])
            })
            atualizados += r.rowcount
        conn.commit()

    return {"fornecedor": fornecedor, "atualizados": atualizados}

@router.get("/precos/resumo")
def resumo_precos():
    """Mostra quantos preços cada fornecedor tem e quando foi a última atualização."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT fornecedor, COUNT(*) as total,
                   MAX(atualizado_em) as ultima_atualizacao
            FROM precos
            GROUP BY fornecedor
            ORDER BY fornecedor
        """)).fetchall()
    return [dict(r._mapping) for r in rows]