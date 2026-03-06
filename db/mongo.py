from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from config import MONGODB_URI, MONGODB_DB_NAME

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect() -> AsyncIOMotorDatabase:
    global _client, _db
    _client = AsyncIOMotorClient(MONGODB_URI)
    _db = _client[MONGODB_DB_NAME]
    await _db.users.create_index("user_id", unique=True)
    return _db


async def disconnect():
    global _client, _db
    if _client:
        _client.close()
    _client = None
    _db = None


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not connected. Call connect() first.")
    return _db
