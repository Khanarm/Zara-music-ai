# database/mongodb.py

import logging
from typing import Optional

from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorDatabase,
    AsyncIOMotorCollection,
)
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

from config import (
    MONGO_URI,
    DB_NAME,
)


logger = logging.getLogger(__name__)


# ============================================================
# DATABASE MANAGER
# ============================================================

class Database:
    """
    MongoDB connection manager for Zara AI.
    """

    def __init__(self) -> None:
        self.client: Optional[
            AsyncIOMotorClient
        ] = None

        self.db: Optional[
            AsyncIOMotorDatabase
        ] = None

        self._connected: bool = False


# Global database instance
db_instance = Database()


# ============================================================
# CONNECT
# ============================================================

async def connect_db() -> AsyncIOMotorDatabase:
    """
    Connect to MongoDB and initialize required indexes.

    Safe to call multiple times.
    """

    if (
        db_instance.client is not None
        and db_instance.db is not None
        and db_instance._connected
    ):
        return db_instance.db

    if not MONGO_URI:
        raise RuntimeError(
            "MONGO_URI is not configured."
        )

    try:
        logger.info(
            "Connecting to MongoDB..."
        )

        db_instance.client = AsyncIOMotorClient(
            MONGO_URI,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            socketTimeoutMS=20000,
            retryWrites=True,
        )

        db_instance.db = db_instance.client[
            DB_NAME
        ]

        # Verify connection.
        await db_instance.client.admin.command(
            "ping"
        )

        db_instance._connected = True

        await create_indexes()

        logger.info(
            "MongoDB connected successfully: %s",
            DB_NAME,
        )

        return db_instance.db

    except Exception:
        logger.exception(
            "MongoDB connection failed."
        )

        if db_instance.client is not None:
            db_instance.client.close()

        db_instance.client = None
        db_instance.db = None
        db_instance._connected = False

        raise


# ============================================================
# ALIASES FOR COMPATIBILITY
# ============================================================

async def init_database() -> AsyncIOMotorDatabase:
    """
    Compatibility wrapper used by main.py.
    """
    return await connect_db()


async def init_db() -> AsyncIOMotorDatabase:
    """
    Compatibility wrapper for older modules.
    """
    return await connect_db()


async def close_database() -> None:
    """
    Compatibility wrapper used by main.py.
    """
    await close_db()


# ============================================================
# CLOSE
# ============================================================

async def close_db() -> None:
    """
    Close MongoDB connection gracefully.
    """

    if db_instance.client is not None:
        logger.info(
            "Closing MongoDB connection..."
        )

        db_instance.client.close()

    db_instance.client = None
    db_instance.db = None
    db_instance._connected = False

    logger.info(
        "MongoDB connection closed."
    )


# ============================================================
# GET DATABASE
# ============================================================

def get_db() -> AsyncIOMotorDatabase:
    """
    Return the currently initialized MongoDB database.

    connect_db() should normally be called during
    application startup before using this function.
    """

    if db_instance.db is None:
        raise RuntimeError(
            "MongoDB is not connected. "
            "Call connect_db() during startup."
        )

    return db_instance.db


# ============================================================
# COLLECTION HELPERS
# ============================================================

def get_users_collection() -> AsyncIOMotorCollection:
    return get_db()["users"]


def get_groups_collection() -> AsyncIOMotorCollection:
    return get_db()["groups"]


def get_subscriptions_collection() -> AsyncIOMotorCollection:
    return get_db()["subscriptions"]


def get_payments_collection() -> AsyncIOMotorCollection:
    return get_db()["payments"]


def get_settings_collection() -> AsyncIOMotorCollection:
    return get_db()["settings"]


def get_memory_collection() -> AsyncIOMotorCollection:
    return get_db()["memory"]


# ============================================================
# SHORT COLLECTION ALIASES
# ============================================================

def users() -> AsyncIOMotorCollection:
    """
    Users collection.
    """
    return get_users_collection()


def groups() -> AsyncIOMotorCollection:
    """
    Groups collection.
    """
    return get_groups_collection()


def subscriptions() -> AsyncIOMotorCollection:
    """
    Subscriptions collection.
    """
    return get_subscriptions_collection()


def payments() -> AsyncIOMotorCollection:
    """
    Payments collection.
    """
    return get_payments_collection()


def settings() -> AsyncIOMotorCollection:
    """
    Settings collection.
    """
    return get_settings_collection()


def memory() -> AsyncIOMotorCollection:
    """
    AI conversation memory collection.
    """
    return get_memory_collection()


# ============================================================
# INDEX CREATION
# ============================================================

async def create_indexes() -> None:
    """
    Create all MongoDB indexes required by Zara AI.

    Index creation is idempotent, so it is safe to call
    during every startup.
    """

    database = get_db()

    users_collection = database["users"]
    groups_collection = database["groups"]
    subscriptions_collection = database[
        "subscriptions"
    ]
    payments_collection = database["payments"]
    settings_collection = database["settings"]
    memory_collection = database["memory"]

    try:

        # ====================================================
        # USERS
        # ====================================================

        await users_collection.create_index(
            [
                (
                    "user_id",
                    ASCENDING,
                )
            ],
            unique=True,
            name="unique_user_id",
        )

        await users_collection.create_index(
            [
                (
                    "username",
                    ASCENDING,
                )
            ],
            name="username_index",
        )

        await users_collection.create_index(
            [
                (
                    "last_seen_at",
                    DESCENDING,
                )
            ],
            name="last_seen_index",
        )

        # ====================================================
        # GROUPS
        # ====================================================

        await groups_collection.create_index(
            [
                (
                    "group_id",
                    ASCENDING,
                )
            ],
            unique=True,
            name="unique_group_id",
        )

        await groups_collection.create_index(
            [
                (
                    "is_active",
                    ASCENDING,
                )
            ],
            name="group_active_index",
        )

        # ====================================================
        # SUBSCRIPTIONS
        # ====================================================

        await subscriptions_collection.create_index(
            [
                (
                    "user_id",
                    ASCENDING,
                ),
                (
                    "group_id",
                    ASCENDING,
                ),
            ],
            unique=True,
            name="unique_user_group_subscription",
        )

        await subscriptions_collection.create_index(
            [
                (
                    "status",
                    ASCENDING,
                ),
                (
                    "expires_at",
                    ASCENDING,
                ),
            ],
            name="subscription_expiry_index",
        )

        await subscriptions_collection.create_index(
            [
                (
                    "user_id",
                    ASCENDING,
                ),
                (
                    "status",
                    ASCENDING,
                ),
            ],
            name="user_subscription_status_index",
        )

        await subscriptions_collection.create_index(
            [
                (
                    "group_id",
                    ASCENDING,
                ),
                (
                    "status",
                    ASCENDING,
                ),
            ],
            name="group_subscription_status_index",
        )

        # ====================================================
        # PAYMENTS
        # ====================================================

        await payments_collection.create_index(
            [
                (
                    "payment_id",
                    ASCENDING,
                )
            ],
            unique=True,
            name="unique_payment_id",
        )

        await payments_collection.create_index(
            [
                (
                    "telegram_payment_charge_id",
                    ASCENDING,
                )
            ],
            unique=True,
            sparse=True,
            name="unique_telegram_charge_id",
        )

        await payments_collection.create_index(
            [
                (
                    "user_id",
                    ASCENDING,
                ),
                (
                    "created_at",
                    DESCENDING,
                ),
            ],
            name="user_payment_history_index",
        )

        await payments_collection.create_index(
            [
                (
                    "group_id",
                    ASCENDING,
                ),
                (
                    "created_at",
                    DESCENDING,
                ),
            ],
            name="group_payment_history_index",
        )

        # ====================================================
        # SETTINGS
        # ====================================================

        await settings_collection.create_index(
            [
                (
                    "key",
                    ASCENDING,
                )
            ],
            unique=True,
            name="unique_setting_key",
        )

        # ====================================================
        # AI MEMORY
        # ====================================================

        await memory_collection.create_index(
            [
                (
                    "user_id",
                    ASCENDING,
                ),
                (
                    "chat_id",
                    ASCENDING,
                ),
                (
                    "created_at",
                    DESCENDING,
                ),
            ],
            name="user_chat_memory_history_index",
        )

        await memory_collection.create_index(
            [
                (
                    "user_id",
                    ASCENDING,
                ),
                (
                    "role",
                    ASCENDING,
                ),
                (
                    "created_at",
                    DESCENDING,
                ),
            ],
            name="user_memory_role_index",
        )

        logger.info(
            "MongoDB indexes initialized successfully."
        )

    except PyMongoError:
        logger.exception(
            "Failed to create MongoDB indexes."
        )
        raise


# ============================================================
# DATABASE HEALTH
# ============================================================

async def ping_db() -> bool:
    """
    Check whether MongoDB is reachable.
    """

    if db_instance.client is None:
        return False

    try:
        await db_instance.client.admin.command(
            "ping"
        )

        return True

    except Exception:
        logger.exception(
            "MongoDB ping failed."
        )

        return False


# ============================================================
# CONNECTION STATUS
# ============================================================

def is_connected() -> bool:
    """
    Return current local connection state.
    """

    return bool(
        db_instance.client is not None
        and db_instance.db is not None
        and db_instance._connected
    )


# ============================================================
# DATABASE NAME
# ============================================================

def get_database_name() -> str:
    """
    Return configured database name.
    """

    return DB_NAME


# ============================================================
# LEGACY DATABASE ACCESS
# ============================================================

@property
def db():
    """
    Legacy compatibility placeholder.

    New code should use get_db().
    """
    return get_db()
