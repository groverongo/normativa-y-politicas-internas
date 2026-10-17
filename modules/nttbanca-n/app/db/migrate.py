"""Migraciones SQL versionadas, sin dependencias extra.

Cada archivo migrations/NNNN_descripcion.sql se aplica una sola vez, en orden, y queda
registrado en la tabla schema_migrations. Todo corre en una sola transacción: si una
migración falla, no queda ninguna aplicada a medias.

Esta es la única secuencia de migraciones del monorepo: ingesta y nttbanca-n
comparten una sola base de datos, y modules/ingesta ya no se auto-migra (ver
migrations/README.md) -- corre esto antes de usar STORAGE_BACKEND=postgres
en ingesta.

Uso, desde la raíz del proyecto:
    python -m app.db.migrate             aplica las pendientes
    python -m app.db.migrate --status    muestra aplicadas y pendientes
    python -m app.db.migrate --dry-run   aplica y deshace todo (para probar)
"""

import argparse
from pathlib import Path

from sqlalchemy import Connection, Engine, text

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

# Lock de Postgres para que dos procesos (p. ej. la EC2 y tu PC) no migren a la vez.
_LOCK_ID = 4172031


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def _applied_versions(conn: Connection) -> set[str]:
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version TEXT PRIMARY KEY,"
            " aplicado_en TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
    )
    return set(conn.scalars(text("SELECT version FROM schema_migrations")))


def run_migrations(engine: Engine, dry_run: bool = False) -> list[str]:
    """Aplica las migraciones pendientes y devuelve sus nombres."""
    applied_now: list[str] = []
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _LOCK_ID})
            applied = _applied_versions(conn)
            for path in migration_files():
                if path.stem in applied:
                    continue
                # Cursor del driver sin parámetros: admite varias sentencias por archivo.
                with conn.connection.cursor() as cursor:
                    cursor.execute(path.read_text(encoding="utf-8"))
                conn.execute(text("INSERT INTO schema_migrations (version) VALUES (:v)"), {"v": path.stem})
                applied_now.append(path.stem)
        except Exception:
            trans.rollback()
            raise
        if dry_run:
            trans.rollback()
        else:
            trans.commit()
    return applied_now


def migration_status(engine: Engine) -> list[tuple[str, bool]]:
    """Solo lectura: no crea schema_migrations si todavía no existe."""
    with engine.connect() as conn:
        exists = conn.scalar(text("SELECT to_regclass('public.schema_migrations')")) is not None
        applied = set(conn.scalars(text("SELECT version FROM schema_migrations"))) if exists else set()
    return [(path.stem, path.stem in applied) for path in migration_files()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Aplica las migraciones SQL de migrations/.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--status", action="store_true", help="muestra aplicadas y pendientes")
    group.add_argument("--dry-run", action="store_true", help="aplica y deshace todo")
    args = parser.parse_args()

    from app.db.session import engine  # usa la conexión del .env

    if args.status:
        for version, applied in migration_status(engine):
            print(f"{'[x]' if applied else '[ ]'} {version}")
        return

    applied_now = run_migrations(engine, dry_run=args.dry_run)
    if not applied_now:
        print("Esquema al día: no hay migraciones pendientes.")
    elif args.dry_run:
        print(f"Dry-run OK, se aplicarían: {', '.join(applied_now)} (no se guardó nada).")
    else:
        print(f"Migraciones aplicadas: {', '.join(applied_now)}")


if __name__ == "__main__":
    main()
