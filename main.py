# main.py

import asyncio
import logging
import signal
from contextlib import suppress

from config import (
    APP_NAME,
    APP_VERSION,
    DEBUG,
    LOG_LEVEL,
    LOG_FILE,
    validate_config,
    get_config_summary,
)


# ============================================================
# LOGGING
# ============================================================

def setup_logging():
    """
    Configure application-wide logging.
    """

    handlers = [
        logging.StreamHandler(),
    ]

    try:
        handlers.append(
            logging.FileHandler(
                LOG_FILE,
                encoding="utf-8",
            )
        )
    except Exception:
        # File logging should never prevent Zara from starting.
        pass

    logging.basicConfig(
        level=getattr(
            logging,
            LOG_LEVEL,
            logging.INFO,
        ),
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
        handlers=handlers,
        force=True,
    )


logger = logging.getLogger("zara")


# ============================================================
# GLOBAL STATE
# ============================================================

_shutdown_event = asyncio.Event()
_tasks = []


# ============================================================
# OPTIONAL MODULE IMPORTS
# ============================================================

async def initialize_database():
    """
    Initialize MongoDB connection.
    """

    try:
        from database.mongodb import init_database

        result = init_database()

        if asyncio.iscoroutine(result):
            await result

        logger.info("MongoDB initialized.")

    except ImportError:
        logger.warning(
            "database.mongodb is not ready yet. "
            "Database initialization skipped."
        )

    except Exception:
        logger.exception(
            "MongoDB initialization failed."
        )
        raise


async def initialize_telegram():
    """
    Initialize Telegram clients/bot and start bot polling.
    """

    try:
        from telegram.client import (
            start_telegram,
            start_polling,
        )

        result = await start_telegram()

        logger.info(
            "Telegram system initialized."
        )

        # ----------------------------------------------------
        # Start Aiogram polling in background
        # ----------------------------------------------------

        polling_task = asyncio.create_task(
            start_polling()
        )

        logger.info(
            "Telegram bot polling started."
        )

        return polling_task

    except ImportError:
        logger.warning(
            "telegram.client is not ready yet. "
            "Telegram initialization skipped."
        )

        return None

    except Exception:
        logger.exception(
            "Telegram initialization failed."
        )
        raise

async def initialize_scheduler():
    """
    Initialize background scheduler if available.
    """

    try:
        from utils.scheduler import start_scheduler

        result = start_scheduler()

        if asyncio.iscoroutine(result):
            result = await result

        logger.info(
            "Scheduler initialized."
        )

        return result

    except ImportError:
        logger.exception(
           "Telegram initialization import failed."
        )
    raise

        return None

    except Exception:
        logger.exception(
            "Scheduler initialization failed."
        )
        raise


# ============================================================
# STARTUP
# ============================================================

async def startup():
    """
    Start all Zara services.
    """

    logger.info("=" * 60)
    logger.info(
        "Starting %s v%s",
        APP_NAME,
        APP_VERSION,
    )
    logger.info("=" * 60)

    # --------------------------------------------------------
    # Validate configuration
    # --------------------------------------------------------

    logger.info(
        "Validating configuration..."
    )

    validate_config()

    logger.info(
        "Configuration validated successfully."
    )

    # --------------------------------------------------------
    # Safe configuration summary
    # --------------------------------------------------------

    summary = get_config_summary()

    logger.info(
        "Environment: %s",
        summary["environment"],
    )

    logger.info(
        "AI: %s (%s)",
        summary["ai_name"],
        summary["gemini_model"],
    )

    logger.info(
        "Voice enabled: %s",
        summary["voice_enabled"],
    )

    logger.info(
        "Music enabled: %s",
        summary["music_enabled"],
    )

    logger.info(
        "Subscriptions enabled: %s",
        summary["subscriptions_enabled"],
    )

    # --------------------------------------------------------
    # Database
    # --------------------------------------------------------

    logger.info(
        "Initializing database..."
    )

    await initialize_database()

    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------

    logger.info(
        "Initializing Telegram..."
    )

    telegram_result = await initialize_telegram()

    if telegram_result is not None:
        _tasks.append(
            telegram_result
        )

    # --------------------------------------------------------
    # Scheduler
    # --------------------------------------------------------

    logger.info(
        "Initializing scheduler..."
    )

    scheduler_result = await initialize_scheduler()

    if scheduler_result is not None:
        _tasks.append(
            scheduler_result
        )

    # --------------------------------------------------------
    # Startup complete
    # --------------------------------------------------------

    logger.info("=" * 60)
    logger.info(
        "%s is now ONLINE.",
        APP_NAME,
    )
    logger.info("=" * 60)


# ============================================================
# SHUTDOWN
# ============================================================

async def shutdown():
    """
    Gracefully stop all Zara services.
    """

    logger.info("=" * 60)
    logger.info(
        "Shutting down %s...",
        APP_NAME,
    )

    # --------------------------------------------------------
    # Stop running tasks
    # --------------------------------------------------------

    for task in list(_tasks):
        try:
            if asyncio.isfuture(task) or isinstance(
                task,
                asyncio.Task,
            ):
                if not task.done():
                    task.cancel()

                    with suppress(
                        asyncio.CancelledError
                    ):
                        await task

        except Exception:
            logger.exception(
                "Error while stopping background task."
            )

    _tasks.clear()

    # --------------------------------------------------------
    # Stop Telegram
    # --------------------------------------------------------

    try:
        from telegram.client import stop_telegram

        result = stop_telegram()

        if asyncio.iscoroutine(result):
            await result

        logger.info(
            "Telegram stopped."
        )

    except ImportError:
        pass

    except Exception:
        logger.exception(
            "Error while stopping Telegram."
        )

    # --------------------------------------------------------
    # Stop database
    # --------------------------------------------------------

    try:
        from database.mongodb import close_database

        result = close_database()

        if asyncio.iscoroutine(result):
            await result

        logger.info(
            "Database connection closed."
        )

    except ImportError:
        pass

    except Exception:
        logger.exception(
            "Error while closing database."
        )

    logger.info(
        "%s stopped successfully.",
        APP_NAME,
    )

    logger.info("=" * 60)


# ============================================================
# SIGNAL HANDLER
# ============================================================

def setup_signal_handlers(loop):
    """
    Register SIGINT/SIGTERM handlers.
    """

    def request_shutdown():
        logger.info(
            "Shutdown signal received."
        )

        if not _shutdown_event.is_set():
            _shutdown_event.set()

    for sig in (
        signal.SIGINT,
        signal.SIGTERM,
    ):
        try:
            loop.add_signal_handler(
                sig,
                request_shutdown,
            )

        except (
            NotImplementedError,
            RuntimeError,
        ):
            # Some platforms don't support
            # add_signal_handler.
            pass


# ============================================================
# APPLICATION RUNNER
# ============================================================

async def run():
    """
    Main application lifecycle.
    """

    await startup()

    try:
        # Keep application alive until
        # shutdown signal is received.
        await _shutdown_event.wait()

    except asyncio.CancelledError:
        logger.info(
            "Main application task cancelled."
        )

    finally:
        await shutdown()


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    """
    Synchronous application entry point.
    """

    setup_logging()

    loop = asyncio.new_event_loop()

    asyncio.set_event_loop(loop)

    setup_signal_handlers(loop)

    try:
        loop.run_until_complete(
            run()
        )

    except KeyboardInterrupt:
        logger.info(
            "Keyboard interrupt received."
        )

    except Exception:
        logger.exception(
            "Fatal application error."
        )

    finally:
        # Cancel any remaining tasks.
        pending = asyncio.all_tasks(
            loop
        )

        for task in pending:
            task.cancel()

        if pending:
            with suppress(
                asyncio.CancelledError
            ):
                loop.run_until_complete(
                    asyncio.gather(
                        *pending,
                        return_exceptions=True,
                    )
                )

        loop.close()

        logger.info(
            "Event loop closed."
        )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
