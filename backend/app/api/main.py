from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.buyer import router as buyer_router
from app.api.routes.health import router as health_router
from app.api.routes.platform import router as platform_router
from app.api.routes.swarm import router as swarm_router

api_router = APIRouter()
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(buyer_router, tags=["buyer"])
api_router.include_router(health_router, tags=["health"])
api_router.include_router(platform_router, tags=["platform"])
api_router.include_router(swarm_router, tags=["swarm"])
