from datetime import UTC, datetime, timedelta

from app.core.db import SessionLocal
from app.models.identity import User
from app.models.platform import (
    BuyerWallet,
    ImageArtifact,
    ImageOffer,
    Node,
    RuntimeAccessSession,
)
from app.services.usage_billing import charge_due_session_hour


def test_charge_due_session_hour_debits_wallet(monkeypatch) -> None:
    monkeypatch.setattr("app.services.usage_billing.remove_runtime_session_bundle", lambda settings, **kwargs: {"ok": True})
    monkeypatch.setattr("app.services.usage_billing.remove_server_peer", lambda settings, public_key: {"ok": True})
    db = SessionLocal()
    try:
        user = User(email="buyer-charge@example.com", password_hash="hash")
        db.add(user)
        db.flush()
        wallet = BuyerWallet(buyer_user_id=user.id, balance_cny_credits=100.0)
        db.add(wallet)
        node = Node(
            seller_user_id=user.id,
            node_key="charge-node",
            device_fingerprint="charge-device",
            hostname="charge-host",
            system="Linux",
            machine="x86_64",
            capabilities={},
        )
        db.add(node)
        db.flush()
        image = ImageArtifact(
            seller_user_id=user.id,
            node_id=node.id,
            repository="seller/charge-demo",
            tag="v1",
            digest="sha256:charge",
            registry="registry.example.com",
            status="uploaded",
        )
        db.add(image)
        db.flush()
        offer = ImageOffer(
            seller_user_id=user.id,
            node_id=node.id,
            image_artifact_id=image.id,
            repository=image.repository,
            tag=image.tag,
            digest=image.digest,
            runtime_image_ref="registry.example.com/seller/charge-demo:v1",
            offer_status="active",
            probe_status="completed",
            probe_measured_capabilities={},
            current_billable_price_cny_per_hour=30.0,
        )
        db.add(offer)
        db.flush()
        session = RuntimeAccessSession(
            buyer_user_id=user.id,
            seller_node_id=node.id,
            image_artifact_id=image.id,
            image_offer_id=offer.id,
            runtime_image=offer.runtime_image_ref,
            code_filename="__shell__",
            code_sha256="shell-session",
            service_name="buyer-runtime-charge",
            config_name="buyer-config-charge",
            connect_code="connect",
            session_token="token",
            status="running",
            command=["sh"],
            started_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1, minutes=5),
        )
        db.add(session)
        db.commit()

        charge = charge_due_session_hour(db, session, now=datetime.now(UTC).replace(tzinfo=None))

        assert charge is not None
        db.refresh(wallet)
        db.refresh(session)
        assert wallet.balance_cny_credits == 70.0
        assert session.accrued_usage_cny == 30.0
        assert session.billed_through is not None
    finally:
        db.close()


def test_charge_due_session_hour_stops_when_debt_limit_exceeded(monkeypatch) -> None:
    monkeypatch.setattr("app.services.usage_billing.remove_runtime_session_bundle", lambda settings, **kwargs: {"ok": True})
    monkeypatch.setattr("app.services.usage_billing.remove_server_peer", lambda settings, public_key: {"ok": True})
    db = SessionLocal()
    try:
        user = User(email="buyer-debt@example.com", password_hash="hash")
        db.add(user)
        db.flush()
        wallet = BuyerWallet(buyer_user_id=user.id, balance_cny_credits=-25.0)
        db.add(wallet)
        node = Node(
            seller_user_id=user.id,
            node_key="debt-node",
            device_fingerprint="debt-device",
            hostname="debt-host",
            system="Linux",
            machine="x86_64",
            capabilities={},
        )
        db.add(node)
        db.flush()
        image = ImageArtifact(
            seller_user_id=user.id,
            node_id=node.id,
            repository="seller/debt-demo",
            tag="v1",
            digest="sha256:debt",
            registry="registry.example.com",
            status="uploaded",
        )
        db.add(image)
        db.flush()
        offer = ImageOffer(
            seller_user_id=user.id,
            node_id=node.id,
            image_artifact_id=image.id,
            repository=image.repository,
            tag=image.tag,
            digest=image.digest,
            runtime_image_ref="registry.example.com/seller/debt-demo:v1",
            offer_status="active",
            probe_status="completed",
            probe_measured_capabilities={},
            current_billable_price_cny_per_hour=30.0,
        )
        db.add(offer)
        db.flush()
        session = RuntimeAccessSession(
            buyer_user_id=user.id,
            seller_node_id=node.id,
            image_artifact_id=image.id,
            image_offer_id=offer.id,
            runtime_image=offer.runtime_image_ref,
            code_filename="__shell__",
            code_sha256="shell-session",
            service_name="buyer-runtime-debt",
            config_name="buyer-config-debt",
            connect_code="connect2",
            session_token="token2",
            status="running",
            command=["sh"],
            started_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1, minutes=5),
        )
        db.add(session)
        db.commit()

        charge = charge_due_session_hour(db, session, now=datetime.now(UTC).replace(tzinfo=None))

        assert charge is None
        db.refresh(wallet)
        db.refresh(session)
        assert wallet.balance_cny_credits == -25.0
        assert session.status == "stopped"
        assert session.ended_at is not None
    finally:
        db.close()
