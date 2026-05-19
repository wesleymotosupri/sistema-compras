from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from app.database import engine
from app.sankhya import buscar_lista_compras
import pandas as pd
import io

router = APIRouter()

FORNECEDORES = ["Embus", "Tmac", "Solidez", "Atacado", "Catimoto", "Atec"]

def _cruzar_precos(produtos: list[dict]) -> list[dict]:
    codigos = [str(p["codigo"]) for p in produtos]
    if not codigos:
        return []

    with engine.connect() as conn:
        placeholders = ",".join([f"'{c}'" for c in codigos])
        vinculos = conn.execute(text(f"""
            SELECT v.meu_codigo, v.fornecedor, v.codigo_fornecedor,
                   COALESCE(p.preco, 0) AS preco
            FROM vinculos v
            LEFT JOIN precos p
              ON p.fornecedor = v.fornecedor
             AND p.codigo_fornecedor = v.codigo_fornecedor
            WHERE v.meu_codigo IN ({placeholders})
        """)).fetchall()

    mapa = {}
    for v in vinculos:
        codigo = v.meu_codigo
        if codigo not in mapa:
            mapa[codigo] = {}
        mapa[codigo][v.fornecedor] = {
            "preco": float(v.preco) if v.preco else None,
            "codigo_fornecedor": v.codigo_fornecedor
        }

    resultado = []
    for p in produtos:
        codigo = str(p["codigo"])
        vinculos_prod = mapa.get(codigo, {})

        precos_forn = {}
        for forn in FORNECEDORES:
            info = vinculos_prod.get(forn)
            precos_forn[forn] = {
                "preco": info["preco"] if info and info["preco"] else None,
                "codigo_fornecedor": info["codigo_fornecedor"] if info else None
            }

        disponiveis = {f: v for f, v in precos_forn.items() if v["preco"]}
        if disponiveis:
            melhor = min(disponiveis, key=lambda f: disponiveis[f]["preco"])
        else:
            melhor = None

        resultado.append({
            **p,
            "precos": precos_forn,
            "fornecedor_sugerido": melhor,
            "preco_sugerido": disponiveis[melhor]["preco"] if melhor else None,
            "cod_forn_sugerido": disponiveis[melhor]["codigo_fornecedor"] if melhor else None,
            "tem_vinculo": bool(vinculos_prod)
        })

    return resultado

@router.get("/pedido/sankhya")
def pedido_do_sankhya():
    produtos = buscar_lista_compras()
    return _cruzar_precos(produtos)

@router.post("/pedido/upload")
async def pedido_por_upload(file: UploadFile = File(...)):
    content = await file.read()
    df = pd.read_excel(io.BytesIO(content), dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]

    col_map = {
        "codigo": ["código", "codigo", "codprod", "cod"],
        "descricao": ["descrição", "descricao", "descrprod"],
        "custo": ["custo", "ultimo_custo", "cusger"],
        "sugestao_compra": ["sugestao_giro_criado", "sugestao_compra", "qtd", "quantidade"],
    }
    resultado = {}
    for campo, opcoes in col_map.items():
        for op in opcoes:
            if op in df.columns:
                resultado[campo] = op
                break

    produtos = []
    for _, row in df.iterrows():
        p = {k: row.get(v, "") for k, v in resultado.items()}
        p["codigo"] = str(p.get("codigo", "")).strip()
        if p["codigo"]:
            produtos.append(p)

    return _cruzar_precos(produtos)

@router.post("/pedido/exportar")
async def exportar_pedido(body: dict):
    itens = body.get("itens", [])
    rows = []
    for item in itens:
        if not item.get("fornecedor_selecionado"):
            continue
        rows.append({
            "Código": item.get("codigo"),
            "Descrição": item.get("descricao"),
            "Fornecedor": item.get("fornecedor_selecionado"),
            "Cód. Fornecedor": item.get("cod_forn_selecionado"),
            "Preço": item.get("preco_selecionado"),
            "Qtd.": item.get("sugestao_compra"),
            "Subtotal": item.get("subtotal"),
        })

    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Pedido")
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=pedido.xlsx"}
    )