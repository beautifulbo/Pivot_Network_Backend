from fastapi import APIRouter

from app.core.config import settings
from app.services.image_offer_publishing import run_offer_probe_and_pricing
from app.services.swarm_manager import get_manager_overview, get_worker_join_token
from app.services.wireguard_server import apply_server_peer

from .activity import router as activity_router
from .images import router as images_router
from .nodes import router as nodes_router
from .offers import router as offers_router
from .overview import router as overview_router
from .runtime import router as runtime_router
from .swarm import router as swarm_router

router = APIRouter(prefix="/platform")
router.include_router(nodes_router)
router.include_router(images_router)
router.include_router(offers_router)
router.include_router(activity_router)
router.include_router(overview_router)
router.include_router(runtime_router)
router.include_router(swarm_router)

__all__ = [
    "apply_server_peer",
    "get_manager_overview",
    "get_worker_join_token",
    "router",
    "run_offer_probe_and_pricing",
    "settings",
]
