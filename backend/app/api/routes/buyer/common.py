from __future__ import annotations

from app.models.buyer import BuyerOrder, BuyerWallet, WalletLedger
from app.models.payment import PaymentOrder
from app.models.seller import ImageOffer, Node
from app.schemas.buyer.catalog import BuyerCatalogOfferResponse
from app.schemas.buyer.orders import BuyerOrderResponse
from app.schemas.buyer.payments import BuyerPaymentListItem, BuyerPaymentResponse, BuyerWalletTopupLedgerResponse
from app.schemas.buyer.wallet import BuyerWalletResponse, WalletLedgerResponse


def serialize_wallet(wallet: BuyerWallet) -> BuyerWalletResponse:
    return BuyerWalletResponse(
        buyer_user_id=wallet.buyer_user_id,
        balance_cny_credits=wallet.balance_cny_credits,
        created_at=wallet.created_at,
        updated_at=wallet.updated_at,
    )


def serialize_wallet_ledger(entry: WalletLedger) -> WalletLedgerResponse:
    return WalletLedgerResponse(
        id=entry.id,
        buyer_user_id=entry.buyer_user_id,
        session_id=entry.session_id,
        usage_charge_id=entry.usage_charge_id,
        entry_type=entry.entry_type,
        amount_delta_cny=entry.amount_delta_cny,
        balance_after=entry.balance_after,
        detail=entry.detail,
        created_at=entry.created_at,
    )


def serialize_catalog_offer(offer: ImageOffer, node: Node | None) -> BuyerCatalogOfferResponse:
    return BuyerCatalogOfferResponse(
        offer_id=offer.id,
        seller_node_key=node.node_key if node else "",
        repository=offer.repository,
        tag=offer.tag,
        runtime_image_ref=offer.runtime_image_ref,
        offer_status=offer.offer_status,
        probe_status=offer.probe_status,
        current_billable_price_cny_per_hour=offer.current_billable_price_cny_per_hour,
        pricing_stale_at=offer.pricing_stale_at,
        probe_measured_capabilities=offer.probe_measured_capabilities,
    )


def serialize_order(order: BuyerOrder, offer: ImageOffer | None, node: Node | None) -> BuyerOrderResponse:
    return BuyerOrderResponse(
        id=order.id,
        offer_id=order.offer_id,
        seller_node_key=node.node_key if node else "",
        repository=offer.repository if offer else "",
        tag=offer.tag if offer else "",
        runtime_image_ref=offer.runtime_image_ref if offer else "",
        requested_duration_minutes=order.requested_duration_minutes,
        issued_hourly_price_cny=order.issued_hourly_price_cny,
        order_status=order.order_status,
        license_token=order.license_token,
        license_redeemed_at=order.license_redeemed_at,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


def serialize_topup_ledger(entry: WalletLedger | None) -> BuyerWalletTopupLedgerResponse | None:
    if entry is None:
        return None
    return BuyerWalletTopupLedgerResponse(
        id=entry.id,
        payment_order_id=entry.payment_order_id,
        entry_type=entry.entry_type,
        amount_delta_cny=entry.amount_delta_cny,
        balance_after=entry.balance_after,
        detail=entry.detail,
        created_at=entry.created_at,
    )


def serialize_payment_list_item(payment: PaymentOrder) -> BuyerPaymentListItem:
    return BuyerPaymentListItem(
        id=payment.id,
        payment_no=payment.payment_no,
        payment_type=payment.payment_type,
        amount_cny=payment.amount_cny,
        currency=payment.currency,
        status=payment.status,
        channel=payment.channel,
        subject=payment.subject,
        description=payment.description,
        third_party_txn_id=payment.third_party_txn_id,
        paid_at=payment.paid_at,
        expired_at=payment.expired_at,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
    )


def serialize_payment(payment: PaymentOrder, ledger: WalletLedger | None) -> BuyerPaymentResponse:
    return BuyerPaymentResponse(
        **serialize_payment_list_item(payment).model_dump(),
        latest_ledger_entry=serialize_topup_ledger(ledger),
    )
