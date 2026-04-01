from fastapi import APIRouter

from app.core.config import settings
from app.services.swarm_manager import (
    create_runtime_session_bundle,
    inspect_runtime_session_bundle,
    remove_runtime_session_bundle,
)
from app.services.wireguard_server import apply_server_peer

from .catalog import router as catalog_router
from .orders import router as orders_router
from .payments import router as payments_router
from .runtime_sessions import router as runtime_sessions_router
from .wallet import router as wallet_router

router = APIRouter(prefix="/buyer")
router.include_router(catalog_router)
router.include_router(orders_router)
router.include_router(wallet_router)
router.include_router(payments_router)
router.include_router(runtime_sessions_router)

__all__ = [
    "apply_server_peer",
    "create_runtime_session_bundle",
    "inspect_runtime_session_bundle",
    "remove_runtime_session_bundle",
    "router",
    "settings",
]
