import logging

from app.config import get_settings

logger = logging.getLogger(__name__)


async def create_checkpointer():
    settings = get_settings()

    if settings.use_memory_checkpointer:
        from langgraph.checkpoint.memory import MemorySaver

        logger.info(
            "Using in-memory checkpointer - state will be lost on restart. "
            "Set USE_MEMORY_CHECKPOINTER=false for persistence."
        )
        return MemorySaver()
    else:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        except ImportError as exc:
            raise RuntimeError(
                "Postgres checkpointer requires langgraph-checkpoint-postgres "
                "and psycopg[binary]. Install them or set USE_MEMORY_CHECKPOINTER=true."
            ) from exc

        conn_string = settings.database_url
        if "+asyncpg" in conn_string:
            conn_string = conn_string.replace("postgresql+asyncpg", "postgresql")

        checkpointer = AsyncPostgresSaver.from_conn_string(conn_string)
        await checkpointer.setup()
        logger.info("Using Postgres checkpointer - state persists across restarts.")
        return checkpointer
