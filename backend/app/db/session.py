from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# pool_size/max_overflow/pool_timeout so existem no QueuePool (Postgres em producao) - o SQLite
# usado pelos testes (SingletonThreadPool/NullPool) rejeita esses kwargs na hora de criar o
# engine, entao so sao passados quando o dialeto realmente e postgres.
_pool_kwargs = (
    {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout_seconds,
    }
    if settings.database_url.startswith("postgresql")
    else {}
)

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=settings.db_pool_recycle_seconds,
    **_pool_kwargs,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
