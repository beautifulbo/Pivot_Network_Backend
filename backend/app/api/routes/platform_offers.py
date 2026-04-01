from fastapi import APIRouter

from app.api.routes.platform.offers import router as offers_router

router = APIRouter(prefix="/platform")
router.include_router(offers_router)
