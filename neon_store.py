import os

import psycopg
from pgvector.psycopg import register_vector


VECTOR_TABLE = "hdfc_chunks"


def connect_neon(*, initialize_extension: bool = False):
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")

    connection = psycopg.connect(database_url, connect_timeout=10)
    try:
        if initialize_extension:
            connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(connection)
    except psycopg.Error:
        connection.close()
        raise
    return connection
