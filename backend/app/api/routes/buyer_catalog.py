from fastapi import APIRouter

from app.api.routes.buyer.catalog import router as catalog_router
from app.api.routes.buyer.wallet import router as wallet_router

router = APIRouter(prefix="/buyer")
router.include_router(catalog_router)
router.include_router(wallet_router)
