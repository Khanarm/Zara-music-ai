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
    MONGO_DB_NAME,
    USERS_COLLECTION,
    GROUPS_COLLECTION,
    SUBSCRIPTIONS_COLLECTION,
    PAYMENTS_COLLECTION,
    SETTINGS_COLLECTION,
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

# Compatibility aliases
client = None
db = None


# ============================================================
# CONNECT
# ============================================================

async def connect_db() -> AsyncIOMotorDatabase:
    """
    Connect to MongoDB and initialize required indexes.

    Safe to call multiple times.
    """

    global client, db

    if (
        db_instance.client is not None
        and db_instance.db is not None
        and db_instance._connected
    ):
        return db_instance.db

    if not MONGO_URI:
        raise RuntimeError(
            "MONGODB_URI is not configured."
        )

    if not MONGO_DB_NAME:
        raise RuntimeError(
            "MONGODB_DATABASE is not configured."
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
            MONGO_DB_NAME
        ]

        # Compatibility aliases
        client = db_instance.client
        db = db_instance.db

        # Verify connection
        await db_instance.client.admin.command(
            "ping"
        )

        db_instance._connected = True

        await create_indexes()

        logger.info(
            "MongoDB connected successfully: %s",
            MONGO_DB_NAME,
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

        client = None
        db = None

        raise


# ============================================================
# ALIASES FOR STARTUP COMPATIBILITY
# ============================================================

async def init_db() -> AsyncIOMotorDatabase:
    """
    Compatibility alias for connect_db().
    """

    return await connect_db()


async def init_database() -> AsyncIOMotorDatabase:
    """
    Compatibility alias used by main.py.
    """

    return await connect_db()


# ============================================================
# CLOSE
# ============================================================

async def close_db() -> None:
    """
    Close MongoDB connection gracefully.
    """

    global client, db

    if db_instance.client is not None:
        logger.info(
            "Closing MongoDB connection..."
        )

        db_instance.client.close()

    db_instance.client = None
    db_instance.db = None
    db_instance._connected = False

    client = None
    db = None

    logger.info(
        "MongoDB connection closed."
    )


# ============================================================
# GET DATABASE
# ============================================================

def get_db() -> AsyncIOMotorDatabase:
    """
    Return the currently initialized MongoDB database.

    connect_db() should normally be called during application
    startup before using this function.
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
    return get_db()[USERS_COLLECTION]


def get_groups_collection() -> AsyncIOMotorCollection:
    return get_db()[GROUPS_COLLECTION]


def get_subscriptions_collection() -> AsyncIOMotorCollection:
    return get_db()[SUBSCRIPTIONS_COLLECTION]


def get_payments_collection() -> AsyncIOMotorCollection:
    return get_db()[PAYMENTS_COLLECTION]


def get_settings_collection() -> AsyncIOMotorCollection:
    return get_db()[SETTINGS_COLLECTION]


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


# ============================================================
# INDEX CREATION
# ============================================================

async def create_indexes() -> None:
    """
    Create all MongoDB indexes required by Zara AI.

    Index creation is idempotent, so it is safe to call during
    every startup.
    """

    database = get_db()

    users_collection = database[
        USERS_COLLECTION
    ]

    groups_collection = database[
        GROUPS_COLLECTION
    ]

    subscriptions_collection = database[
        SUBSCRIPTIONS_COLLECTION
    ]

    payments_collection = database[
        PAYMENTS_COLLECTION
    ]

    settings_collection = database[
        SETTINGS_COLLECTION
    ]

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

    return MONGO_DB_NAME


# ============================================================
# DATABASE OBJECT
# ============================================================

def get_database() -> AsyncIOMotorDatabase:
    """
    Compatibility alias for get_db().
    """

    return get_db()
