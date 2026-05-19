import requests
import os
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv("SANKHYA_CLIENT_ID")
client_secret = os.getenv("SANKHYA_CLIENT_SECRET")
x_token = os.getenv("SANKHYA_TOKEN_GATEWAY")

def autenticar():
    response = requests.post(
        "https://api.sankhya.com.br/authenticate",
        headers={"X-Token": x_token},
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret
        },
        timeout=30
    )
    return response.json()["access_token"]

def executar_sql(sql):
    token = autenticar()
    payload = {
        "serviceName": "DbExplorerSP.executeQuery",
        "requestBody": {
            "sql": sql
        }
    }
    response = requests.post(
        "https://api.sankhya.com.br/gateway/v1/mge/service.sbr?serviceName=DbExplorerSP.executeQuery&outputType=json",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Token": x_token,
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=60
    )
    return response.json()

def extrair_rows(dados):
    return dados.get("responseBody", {}).get("rows", [])

QUERY_COMPRAS = """
WITH PARAMS AS (
    SELECT 3 AS MESES_ANALISE, 22 AS DIAS_UTEIS_MES, 7 AS DIAS_COBERTURA, 1.2 AS FATOR_SEGURANCA
),
VENDAS AS (
    SELECT TGFITE.CODPROD, SUM(TGFITE.QTDNEG) AS TOTAL_VENDAS
    FROM TGFITE
    JOIN TGFCAB ON TGFITE.NUNOTA = TGFCAB.NUNOTA
    CROSS JOIN PARAMS
    WHERE TGFCAB.DTNEG >= DATEADD(MONTH, -PARAMS.MESES_ANALISE, GETDATE())
      AND TGFCAB.CODTIPOPER = 1100
    GROUP BY TGFITE.CODPROD
),
CALCULO_GIRO AS (
    SELECT V.CODPROD,
           V.TOTAL_VENDAS * 1.0 / (PARAMS.MESES_ANALISE * PARAMS.DIAS_UTEIS_MES) AS GIRO_MEDIO_CRIADO
    FROM VENDAS V CROSS JOIN PARAMS
),
CALCULO_SUGESTAO AS (
    SELECT V.CODPROD,
           CEILING(
               (V.TOTAL_VENDAS * 1.0 / (PARAMS.MESES_ANALISE * PARAMS.DIAS_UTEIS_MES)
               * PARAMS.DIAS_COBERTURA * PARAMS.FATOR_SEGURANCA)
               - (COALESCE(E.ESTOQUE, 0) - COALESCE(E.RESERVADO, 0))
           ) AS SUGESTAO_GIRO_CRIADO
    FROM VENDAS V
    JOIN TGFEST E ON V.CODPROD = E.CODPROD AND E.CODLOCAL = 10000000
    CROSS JOIN PARAMS
),
ULTIMA_COMPRA AS (
    SELECT CODPROD, DATA_ULTIMA_COMPRA, QTD_ULTIMA_COMPRA
    FROM (
        SELECT TGFITE.CODPROD, TGFCAB.DTENTSAI AS DATA_ULTIMA_COMPRA,
               TGFITE.QTDNEG AS QTD_ULTIMA_COMPRA,
               ROW_NUMBER() OVER (PARTITION BY TGFITE.CODPROD ORDER BY TGFCAB.DTENTSAI DESC) AS RN
        FROM TGFITE
        JOIN TGFCAB ON TGFITE.NUNOTA = TGFCAB.NUNOTA
        WHERE TGFCAB.CODTIPOPER IN (110, 205, 215)
    ) U WHERE RN = 1
),
ULTIMA_VENDA AS (
    SELECT TGFITE.CODPROD, MAX(TGFCAB.DTNEG) AS DATA_ULTIMA_VENDA
    FROM TGFITE
    JOIN TGFCAB ON TGFITE.NUNOTA = TGFCAB.NUNOTA
    WHERE TGFCAB.CODTIPOPER = 1100
    GROUP BY TGFITE.CODPROD
),
ULTIMO_CUSTO AS (
    SELECT CODPROD, CUSGER AS ULTIMO_CUSTO
    FROM (
        SELECT CODPROD, CUSGER,
               ROW_NUMBER() OVER (PARTITION BY CODPROD ORDER BY DTATUAL DESC) AS RN
        FROM TGFCUS WHERE CODEMP = 1
    ) X WHERE RN = 1
)
SELECT
    P.CODPROD                                          AS codigo,
    P.DESCRPROD                                        AS descricao,
    COALESCE(S.SUGESTAO_GIRO_CRIADO, 0)               AS sugestao_compra,
    COALESCE(E.ESTOQUE, 0) - COALESCE(E.RESERVADO, 0) AS estoque_disponivel,
    DATEDIFF(DAY, UV.DATA_ULTIMA_VENDA, GETDATE())     AS dias_sem_venda,
    ULT.ULTIMO_CUSTO                                   AS custo,
    UC.QTD_ULTIMA_COMPRA                               AS qtd_ultima_compra,
    UC.DATA_ULTIMA_COMPRA                              AS data_ultima_compra,
    C.GIRO_MEDIO_CRIADO                                AS giro_medio,
    UV.DATA_ULTIMA_VENDA                               AS data_ultima_venda
FROM TGFPRO P
LEFT JOIN TGFEST E           ON P.CODPROD = E.CODPROD AND E.CODLOCAL = 10000000
LEFT JOIN CALCULO_GIRO C     ON P.CODPROD = C.CODPROD
LEFT JOIN CALCULO_SUGESTAO S ON P.CODPROD = S.CODPROD
LEFT JOIN ULTIMA_COMPRA UC   ON P.CODPROD = UC.CODPROD
LEFT JOIN ULTIMA_VENDA UV    ON P.CODPROD = UV.CODPROD
LEFT JOIN ULTIMO_CUSTO ULT   ON P.CODPROD = ULT.CODPROD
WHERE P.AD_APOIOCOMPRAS LIKE '%IMPORT%'
  AND P.AD_APOIOCOMPRAS NOT LIKE '%EXCLUSIVO%'
  AND P.ATIVO = 'S'
  AND COALESCE(S.SUGESTAO_GIRO_CRIADO, 0) > 0
"""

def buscar_lista_compras():
    dados = executar_sql(QUERY_COMPRAS)
    rows = extrair_rows(dados)
    fields = [f["name"].lower() for f in dados.get("responseBody", {}).get("fieldsMetadata", [])]
    return [dict(zip(fields, row)) for row in rows]