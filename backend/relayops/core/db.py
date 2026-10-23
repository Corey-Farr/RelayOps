from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from relayops.core.config import settings

engine = create_async_engine(settings().database_url, pool_pre_ping=True, pool_size=15, max_overflow=10)
Session = async_sessionmaker(engine, expire_on_commit=False)


async def session():
    async with Session() as db:
        yield db
