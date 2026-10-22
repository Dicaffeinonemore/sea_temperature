from collections.abc import Iterator

import psycopg
from psycopg.rows import dict_row

from backend.config import get_settings


def connect() -> psycopg.Connection:
    # Supabase transaction pooling does not support prepared statements.
    return psycopg.connect(
        **get_settings().connection_kwargs(), row_factory=dict_row, prepare_threshold=None,
    )


def get_db() -> Iterator[psycopg.Connection]:
    # One read-only transaction per request; close/rollback on all exit paths.
    with connect() as conn:
        conn.read_only = True
        # Transaction-local settings also work when a pooler reuses server sessions.
        conn.execute("SELECT set_config('TimeZone', 'Asia/Seoul', true)")
        conn.execute(
            "SELECT set_config('statement_timeout', %s, true)",
            (str(get_settings().db_statement_timeout_ms),),
        )
        yield conn


def get_customer_db() -> Iterator[psycopg.Connection]:
    """Commit a successful customer request, roll back any failed request."""
    with connect() as conn:
        conn.execute("SELECT set_config('TimeZone', 'Asia/Seoul', true)")
        conn.execute(
            "SELECT set_config('statement_timeout', %s, true)",
            (str(get_settings().db_statement_timeout_ms),),
        )
        yield conn
