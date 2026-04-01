from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.buyer.common import serialize_payment, serialize_payment_list_item
from app.core.db import get_db
from app.models.identity import User
from app.schemas.buyer.payments import (
    BuyerPaymentConfirmRequest,
    BuyerPaymentCreateRequest,
    BuyerPaymentListItem,
    BuyerPaymentResponse,
)
from app.services.buyer_payments import (
    confirm_payment_order,
    create_payment_order,
    get_buyer_payment,
    get_payment_topup_ledger,
    list_buyer_payments,
)

router = APIRouter()


@router.post("/payments", response_model=BuyerPaymentResponse, status_code=status.HTTP_201_CREATED)
def create_buyer_payment(
    payload: BuyerPaymentCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerPaymentResponse:
    payment = create_payment_order(
        db,
        buyer_user_id=current_user.id,
        amount_cny=payload.amount_cny,
        channel=payload.channel,
        subject=payload.subject,
        description=payload.description,
        expires_minutes=payload.expires_minutes,
    )
    return serialize_payment(payment, None)


@router.get("/payments", response_model=list[BuyerPaymentListItem])
def list_buyer_payments_route(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BuyerPaymentListItem]:
    return [serialize_payment_list_item(payment) for payment in list_buyer_payments(db, current_user.id)]


@router.get("/payments/{payment_id}", response_model=BuyerPaymentResponse)
def read_buyer_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerPaymentResponse:
    payment = get_buyer_payment(db, buyer_user_id=current_user.id, payment_id=payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found.")
    return serialize_payment(payment, get_payment_topup_ledger(db, payment.id))


@router.post("/payments/{payment_id}/confirm", response_model=BuyerPaymentResponse)
def confirm_buyer_payment(
    payment_id: int,
    payload: BuyerPaymentConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BuyerPaymentResponse:
    payment = get_buyer_payment(db, buyer_user_id=current_user.id, payment_id=payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found.")
    try:
        payment, ledger = confirm_payment_order(
            db,
            payment_order=payment,
            status=payload.status,
            third_party_txn_id=payload.third_party_txn_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return serialize_payment(payment, ledger)
