
import logging

from fastapi import FastAPI, HTTPException
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import engine
from app.logging_config import configure_logging
from app.redis_client import check_redis
from app.routers import restaurants, menu, carts, orders
from app.middleware import RequestLoggingMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

# Configure application logging
configure_logging()
logger = logging.getLogger(__name__)


app = FastAPI(
    title="Food Delivery Platform API",
    version="1.0.0",
)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Register API routers
app.include_router(restaurants.router)
app.include_router(menu.router)
app.include_router(carts.router)
app.include_router(orders.router)
app.add_middleware(RequestLoggingMiddleware)

@app.get("/")
def root():
    logger.info("Root endpoint requested")

    return {
        "message": "Food Delivery Platform API is running",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health():
    """Check whether PostgreSQL and Redis are reachable."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        check_redis()

        logger.info("Health check passed")

        return {
            "status": "healthy",
            "postgresql": "connected",
            "redis": "connected",
        }

    except (SQLAlchemyError, RedisError):
        logger.exception("Health check failed")

        raise HTTPException(
            status_code=503,
            detail="A required service is unavailable",
        )


@app.get("/health/db")
def database_health():
    """Check PostgreSQL connectivity."""
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("SELECT current_database(), current_user")
            ).one()

        logger.info("Database health check passed")

        return {
            "status": "connected",
            "database": result[0],
            "user": result[1],
        }

    except SQLAlchemyError:
        logger.exception("Database health check failed")

        raise HTTPException(
            status_code=503,
            detail="Could not connect to PostgreSQL",
        )
