import requests
import os
from dotenv import load_dotenv

load_dotenv()

client_id     = os.getenv("SANKHYA_CLIENT_ID")
client_secret = os.getenv("SANKHYA_CLIENT_SECRET")
x_token       = os.getenv("SANKHYA_TOKEN_GATEWAY")

def autenticar():
    response = requests.post(
        "https://api.sankhya.com.br/authenticate",
        headers={"X-Token": x_token},
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret
        },
        timeout=60
    )
    return response.json()["access_token"]

def executar_sql(sql):
    token = autenticar()
    payload = {
        "serviceName": "DbExplorerSP.executeQuery",
        "requestBody": {"sql": sql}
    }
    response = requests.post(
        "https://api.sankhya.com.br/gateway/v1/mge/service.sbr?serviceName=DbExplorerSP.executeQuery&outputType=json",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Token": x_token,
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=120
    )
    return response.json()

def extrair_rows(dados):
    return dados.get("responseBody", {}).get("rows", [])


def buscar_apoio_compras():
    """Retorna todos os valores distintos de AD_APOIOCOMPRAS do Sankhya."""
    sql = """
        SELECT DISTINCT AD_APOIOCOMPRAS
        FROM TGFPRO
        WHERE ATIVO = 'S'
        AND AD_APOIOCOMPRAS IS NOT NULL
        ORDER BY AD_APOIOCOMPRAS
    """
    dados = executar_sql(sql)
    rows = extrair_rows(dados)
    return [r[0] for r in rows if r[0]]


def buscar_marcas():
    """Retorna todas as marcas distintas do cadastro de produtos."""
    sql = """
        SELECT DISTINCT MARCA
        FROM TGFPRO
        WHERE ATIVO = 'S'
        AND MARCA IS NOT NULL
        AND MARCA <> ''
        ORDER BY MARCA
    """
    dados = executar_sql(sql)
    rows = extrair_rows(dados)
    return [r[0] for r in rows if r[0]]


def _lista_sql(valores: str) -> str:
    """Sanitiza uma string 'a,b,c' vinda da tela pra uso seguro em CAST/LIKE."""
    if not valores:
        return ""
    partes = [v.strip() for v in valores.split(",") if v.strip()]
    return ",".join(partes)


def buscar_lista_compras(
    codemp: int,
    codlocal: int,
    dias_uteis_mes: int,
    cobertura_dias: int,
    tipos_venda: str,                       # ex: "1120" ou "1100"
    margem_seguranca: float = 1.2,
    qtd_sem_historico: int = 3,
    tipos_compra: str = "109,110,205,215",
    incluir_apoio: list[str] | None = None,
    excluir_apoio: list[str] | None = None,
    incluir_marca: list[str] | None = None,
    excluir_marca: list[str] | None = None,
):
    """
    Query única de sugestão de compra, usada para as empresas 1, 3 e 4.
    Todos os parâmetros de negócio vêm da tela (nenhum fixo no código).

    Regras:
    - Giro = vendas dos últimos 3 meses / (3 * dias_uteis_mes)
    - Sugestão pelo giro: (giro * cobertura_dias * margem) - estoque_disponivel
    - Se giro não pede compra e ainda tem estoque disponível -> sugestão = 0
    - Se giro não pede compra e estoque <= 0 e já teve compra -> repete última compra
    - Se giro não pede compra e estoque <= 0 e nunca comprou -> usa qtd_sem_historico
    - Custo gerencial sempre da Empresa 1 (mais recente)
    - Estoque disponível na Empresa 1 é sempre calculado e exibido
    - Se codemp != 1: só entram produtos com estoque disponível > 0 na Empresa 1
    """

    tipos_venda_sql  = _lista_sql(tipos_venda)
    tipos_compra_sql = _lista_sql(tipos_compra)

    filtros_apoio_inc = " OR ".join([f"TGFPRO.AD_APOIOCOMPRAS LIKE '%{v}%'" for v in incluir_apoio]) if incluir_apoio else "1=1"
    filtros_apoio_exc = " AND ".join([f"TGFPRO.AD_APOIOCOMPRAS NOT LIKE '%{v}%'" for v in excluir_apoio]) if excluir_apoio else "1=1"
    filtros_marca_inc = " OR ".join([f"TGFPRO.MARCA LIKE '%{v}%'" for v in incluir_marca]) if incluir_marca else "1=1"
    filtros_marca_exc = " AND ".join([f"TGFPRO.MARCA NOT LIKE '%{v}%'" for v in excluir_marca]) if excluir_marca else "1=1"

    # Regra: só filtra por estoque na Empresa 1 quando a empresa selecionada NÃO é a 1
    filtro_estoque_emp1 = "AND COALESCE(ESTOQUE_EMP1.ESTOQUE_DISPONIVEL_EMP1, 0) > 0" if codemp != 1 else ""

    sql = f"""
    WITH PARAMS AS (
        SELECT
            {codemp}            AS CODEMP,
            {codlocal}          AS CODLOCAL,
            {dias_uteis_mes}    AS DIAS_UTEIS_MES,
            {cobertura_dias}    AS COBERTURA_DIAS,
            {margem_seguranca}  AS MARGEM_SEGURANCA,
            {qtd_sem_historico} AS QTD_SEM_HISTORICO,
            '{tipos_venda_sql}'  AS TIPOS_VENDA,
            '{tipos_compra_sql}' AS TIPOS_COMPRA
    ),
    VENDAS AS (
        SELECT
            TGFITE.CODPROD,
            SUM(TGFITE.QTDNEG) AS TOTAL_VENDAS
        FROM
            TGFITE
        JOIN
            TGFCAB ON TGFITE.NUNOTA = TGFCAB.NUNOTA
        CROSS JOIN
            PARAMS
        WHERE
            TGFCAB.DTNEG >= DATEADD(MONTH, -3, GETDATE())
            AND ',' + PARAMS.TIPOS_VENDA + ',' LIKE '%,' + CAST(TGFCAB.CODTIPOPER AS VARCHAR) + ',%'
            AND TGFCAB.CODEMP = PARAMS.CODEMP
        GROUP BY
            TGFITE.CODPROD
    ),
    ESTOQUE AS (
        SELECT
            TGFEST.*,
            ROW_NUMBER() OVER (
                PARTITION BY TGFEST.CODPROD
                ORDER BY CASE WHEN TGFEST.CODLOCAL = PARAMS.CODLOCAL THEN 0 ELSE 1 END
            ) AS RN
        FROM
            TGFEST
        CROSS JOIN
            PARAMS
        WHERE
            TGFEST.CODLOCAL IN (PARAMS.CODLOCAL, 0)
            AND TGFEST.CODEMP = PARAMS.CODEMP
    ),
    ESTOQUE_EMP1 AS (
        SELECT
            TGFEST.CODPROD,
            (TGFEST.ESTOQUE - COALESCE(TGFEST.RESERVADO, 0)) AS ESTOQUE_DISPONIVEL_EMP1
        FROM
            TGFEST
        WHERE
            TGFEST.CODLOCAL = 10000000
            AND TGFEST.CODEMP = 1
    ),
    CUSTO AS (
        -- Custo gerencial sempre da Empresa 1, mais recente por produto
        SELECT
            CODPROD,
            CUSGER,
            DTATUAL
        FROM (
            SELECT
                CODPROD,
                CUSGER,
                DTATUAL,
                ROW_NUMBER() OVER (PARTITION BY CODPROD ORDER BY DTATUAL DESC) AS RN
            FROM
                TGFCUS
            WHERE
                CODEMP = 1
        ) X
        WHERE RN = 1
    ),
    ULTIMA_COMPRA AS (
        SELECT
            I.CODPROD,
            SUM(I.QTDNEG) AS QTD_ULTIMA_COMPRA,
            MAX(C.DTNEG)  AS DATA_ULTIMA_COMPRA
        FROM
            TGFITE I
        JOIN
            TGFCAB C ON I.NUNOTA = C.NUNOTA
        CROSS JOIN
            PARAMS
        JOIN (
            SELECT
                TGFITE.CODPROD,
                MAX(TGFCAB.DTNEG) AS MAX_DATA
            FROM
                TGFITE
            JOIN
                TGFCAB ON TGFITE.NUNOTA = TGFCAB.NUNOTA
            CROSS JOIN
                PARAMS
            WHERE
                ',' + PARAMS.TIPOS_COMPRA + ',' LIKE '%,' + CAST(TGFCAB.CODTIPOPER AS VARCHAR) + ',%'
                AND TGFCAB.CODEMP = PARAMS.CODEMP
            GROUP BY
                TGFITE.CODPROD
        ) UM ON I.CODPROD = UM.CODPROD AND C.DTNEG = UM.MAX_DATA
        WHERE
            ',' + PARAMS.TIPOS_COMPRA + ',' LIKE '%,' + CAST(C.CODTIPOPER AS VARCHAR) + ',%'
            AND C.CODEMP = PARAMS.CODEMP
        GROUP BY
            I.CODPROD
    ),
    RESULTADO AS (
        SELECT
            TGFPRO.CODPROD         AS CODPROD,
            TGFPRO.DESCRPROD       AS DESCRPROD,
            TGFPRO.MARCA           AS MARCA,
            TGFPRO.REFERENCIA      AS REFERENCIA,
            TGFPRO.AD_APOIOCOMPRAS AS AD_APOIOCOMPRAS,
            ESTOQUE.CODLOCAL       AS CODIGO_LOCAL,
            ESTOQUE.ESTOQUE        AS ESTOQUE,
            COALESCE(ESTOQUE.RESERVADO, 0) AS RESERVA,
            CASE
                WHEN (ESTOQUE.ESTOQUE - COALESCE(ESTOQUE.RESERVADO, 0)) < 0 THEN 0
                ELSE (ESTOQUE.ESTOQUE - COALESCE(ESTOQUE.RESERVADO, 0))
            END AS ESTOQUE_DISPONIVEL,
            COALESCE(CUSTO.CUSGER, 0) AS CUSTO_GERENCIAL,
            COALESCE(VENDAS.TOTAL_VENDAS, 0) AS QTD_VENDIDA_3M,
            ROUND(COALESCE(VENDAS.TOTAL_VENDAS, 0) * 1.0 / (3 * PARAMS.DIAS_UTEIS_MES), 2) AS GIRO_DIARIO,
            ULTIMA_COMPRA.QTD_ULTIMA_COMPRA,
            ULTIMA_COMPRA.DATA_ULTIMA_COMPRA,

            CASE
                WHEN CEILING(
                        (COALESCE(VENDAS.TOTAL_VENDAS, 0) * 1.0 / (3 * PARAMS.DIAS_UTEIS_MES)) * PARAMS.COBERTURA_DIAS * PARAMS.MARGEM_SEGURANCA
                        - CASE WHEN (ESTOQUE.ESTOQUE - COALESCE(ESTOQUE.RESERVADO, 0)) < 0 THEN 0 ELSE (ESTOQUE.ESTOQUE - COALESCE(ESTOQUE.RESERVADO, 0)) END
                     ) < 0
                THEN 0
                ELSE CEILING(
                        (COALESCE(VENDAS.TOTAL_VENDAS, 0) * 1.0 / (3 * PARAMS.DIAS_UTEIS_MES)) * PARAMS.COBERTURA_DIAS * PARAMS.MARGEM_SEGURANCA
                        - CASE WHEN (ESTOQUE.ESTOQUE - COALESCE(ESTOQUE.RESERVADO, 0)) < 0 THEN 0 ELSE (ESTOQUE.ESTOQUE - COALESCE(ESTOQUE.RESERVADO, 0)) END
                     )
            END AS SUGESTAO_COMPRA_GIRO,

            CASE
                WHEN CEILING(
                        (COALESCE(VENDAS.TOTAL_VENDAS, 0) * 1.0 / (3 * PARAMS.DIAS_UTEIS_MES)) * PARAMS.COBERTURA_DIAS * PARAMS.MARGEM_SEGURANCA
                        - CASE WHEN (ESTOQUE.ESTOQUE - COALESCE(ESTOQUE.RESERVADO, 0)) < 0 THEN 0 ELSE (ESTOQUE.ESTOQUE - COALESCE(ESTOQUE.RESERVADO, 0)) END
                     ) > 0
                THEN CEILING(
                        (COALESCE(VENDAS.TOTAL_VENDAS, 0) * 1.0 / (3 * PARAMS.DIAS_UTEIS_MES)) * PARAMS.COBERTURA_DIAS * PARAMS.MARGEM_SEGURANCA
                        - CASE WHEN (ESTOQUE.ESTOQUE - COALESCE(ESTOQUE.RESERVADO, 0)) < 0 THEN 0 ELSE (ESTOQUE.ESTOQUE - COALESCE(ESTOQUE.RESERVADO, 0)) END
                     )
                WHEN CASE WHEN (ESTOQUE.ESTOQUE - COALESCE(ESTOQUE.RESERVADO, 0)) < 0 THEN 0 ELSE (ESTOQUE.ESTOQUE - COALESCE(ESTOQUE.RESERVADO, 0)) END > 0
                THEN 0
                WHEN CASE WHEN (ESTOQUE.ESTOQUE - COALESCE(ESTOQUE.RESERVADO, 0)) < 0 THEN 0 ELSE (ESTOQUE.ESTOQUE - COALESCE(ESTOQUE.RESERVADO, 0)) END <= 0
                     AND ULTIMA_COMPRA.QTD_ULTIMA_COMPRA IS NOT NULL
                THEN ULTIMA_COMPRA.QTD_ULTIMA_COMPRA
                WHEN CASE WHEN (ESTOQUE.ESTOQUE - COALESCE(ESTOQUE.RESERVADO, 0)) < 0 THEN 0 ELSE (ESTOQUE.ESTOQUE - COALESCE(ESTOQUE.RESERVADO, 0)) END <= 0
                     AND ULTIMA_COMPRA.QTD_ULTIMA_COMPRA IS NULL
                THEN PARAMS.QTD_SEM_HISTORICO
                ELSE 0
            END AS SUGESTAO_COMPRA_AJUSTADA,

            COALESCE(ESTOQUE_EMP1.ESTOQUE_DISPONIVEL_EMP1, 0) AS ESTOQUE_DISPONIVEL_EMPRESA1

        FROM
            TGFPRO
        CROSS JOIN
            PARAMS
        JOIN
            ESTOQUE ON TGFPRO.CODPROD = ESTOQUE.CODPROD AND ESTOQUE.RN = 1
        LEFT JOIN
            VENDAS ON TGFPRO.CODPROD = VENDAS.CODPROD
        LEFT JOIN
            ULTIMA_COMPRA ON TGFPRO.CODPROD = ULTIMA_COMPRA.CODPROD
        LEFT JOIN
            ESTOQUE_EMP1 ON TGFPRO.CODPROD = ESTOQUE_EMP1.CODPROD
        LEFT JOIN
            CUSTO ON TGFPRO.CODPROD = CUSTO.CODPROD
        WHERE
            TGFPRO.ATIVO = 'S'
            AND ({filtros_apoio_inc})
            AND {filtros_apoio_exc}
            AND ({filtros_marca_inc})
            AND {filtros_marca_exc}
            {filtro_estoque_emp1}
    )
    SELECT *
    FROM RESULTADO
    WHERE SUGESTAO_COMPRA_AJUSTADA > 0
    ORDER BY CODPROD
    """

    dados = executar_sql(sql)
    rows = extrair_rows(dados)
    fields = [f["name"].lower() for f in dados.get("responseBody", {}).get("fieldsMetadata", [])]
    return [dict(zip(fields, row)) for row in rows]