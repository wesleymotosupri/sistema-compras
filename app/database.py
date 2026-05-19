import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL) if DATABASE_URL else None

def init_db():
    if not engine:
        print("⚠️  DATABASE_URL não configurado — banco desativado")
        return
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
        conn.commit()