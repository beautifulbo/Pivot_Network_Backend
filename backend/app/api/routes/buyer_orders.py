from fastapi import APIRouter

from app.api.routes.buyer.orders import router as orders_router

router = APIRouter(prefix="/buyer")
router.include_router(orders_router)
