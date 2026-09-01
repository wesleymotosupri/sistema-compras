from fastapi import APIRouter
from sqlalchemy import text
from app.database import engine

router = APIRouter()


@router.get("/estoque-minimo")
def listar_estoque_minimo():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, padrao, qtd_minima, atualizado_em
            FROM estoque_minimo
            ORDER BY padrao
        """)).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/estoque-minimo/importar")
def importar_estoque_minimo(body: dict):
    """
    Recebe um texto com uma linha por padrão, no formato:
        ANTENA CORTA PIPA = 10
        BATERIA VRLA (GTI 6BS) = 5
    Cada linha vira (ou atualiza) um registro. Linhas mal formatadas são ignoradas.
    """
    texto = body.get("texto", "")
    linhas = [l.strip() for l in texto.split("\n") if l.strip()]

    inseridos = 0
    ignorados = 0

    with engine.connect() as conn:
        for linha in linhas:
            if "=" not in linha:
                ignorados += 1
                continue
            padrao, valor = linha.rsplit("=", 1)
            padrao = padrao.strip().upper()
            valor = valor.strip()
            if not padrao or not valor.isdigit():
                ignorados += 1
                continue
            conn.execute(text("""
                INSERT INTO estoque_minimo (padrao, qtd_minima, atualizado_em)
                VALUES (:padrao, :qtd_minima, NOW())
                ON CONFLICT (padrao) DO UPDATE SET qtd_minima = EXCLUDED.qtd_minima, atualizado_em = NOW()
            """), {"padrao": padrao, "qtd_minima": int(valor)})
            inseridos += 1
        conn.commit()

    return {"inseridos": inseridos, "ignorados": ignorados}


@router.delete("/estoque-minimo/{id}")
def deletar_estoque_minimo(id: int):
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM estoque_minimo WHERE id = :id"), {"id": id})
        conn.commit()
    return {"ok": True}