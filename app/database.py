import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def init_db():
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fornecedores (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL UNIQUE
            );
        """))
        conn.execute(text("""
            INSERT INTO fornecedores (nome)
            VALUES ('Embus'),('Tmac'),('Solidez'),('Atacado'),('Catimoto'),('Atec')
            ON CONFLICT (nome) DO NOTHING;
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS meus_produtos (
                id SERIAL PRIMARY KEY,
                codigo TEXT NOT NULL UNIQUE,
                descricao TEXT NOT NULL
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS vinculos (
                id SERIAL PRIMARY KEY,
                meu_codigo TEXT NOT NULL,
                fornecedor TEXT NOT NULL,
                codigo_fornecedor TEXT NOT NULL,
                UNIQUE (meu_codigo, fornecedor, codigo_fornecedor)
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS precos (
                id SERIAL PRIMARY KEY,
                fornecedor TEXT NOT NULL,
                codigo_fornecedor TEXT NOT NULL,
                preco NUMERIC NOT NULL,
                atualizado_em TIMESTAMP DEFAULT NOW(),
                UNIQUE (fornecedor, codigo_fornecedor)
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pedidos (
                id SERIAL PRIMARY KEY,
                numero TEXT NOT NULL,
                fornecedor TEXT NOT NULL,
                valor_total NUMERIC NOT NULL DEFAULT 0,
                criado_em TIMESTAMP DEFAULT NOW()
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pedido_itens (
                id SERIAL PRIMARY KEY,
                pedido_id INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
                meu_codigo TEXT NOT NULL,
                descricao TEXT,
                codigo_fornecedor TEXT,
                preco NUMERIC NOT NULL DEFAULT 0,
                quantidade INTEGER NOT NULL DEFAULT 0,
                subtotal NUMERIC NOT NULL DEFAULT 0
            );
        """))
        conn.commit()