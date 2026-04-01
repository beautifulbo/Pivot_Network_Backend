from __future__ import annotations

from app.models.activity import ActivityEvent
from app.models.identity import NodeRegistrationToken
from app.models.seller import ImageArtifact, ImageOffer, Node
from app.schemas.activity import ActivityEventResponse
from app.schemas.platform.images import ImageArtifactResponse
from app.schemas.platform.nodes import NodeResponse, NodeTokenListResponse
from app.schemas.platform.offers import ImageOfferResponse
from app.services.platform_nodes import extract_node_wireguard_target


def serialize_node(node: Node) -> NodeResponse:
    wireguard_target = extract_node_wireguard_target(node)
    return NodeResponse(
        id=node.id,
        seller_user_id=node.seller_user_id,
        node_key=node.node_key,
        device_fingerprint=node.device_fingerprint,
        hostname=node.hostname,
        system=node.system,
        machine=node.machine,
        status=node.status,
        shared_percent_preference=node.shared_percent_preference,
        node_class=node.node_class,
        capabilities=node.capabilities,
        seller_intent=node.seller_intent,
        docker_status=node.docker_status,
        swarm_state=node.swarm_state,
        ready_for_registry_push=bool(node.docker_status),
        wireguard_ready_for_buyer=bool(wireguard_target),
        wireguard_target=wireguard_target,
        needs_docker_setup=not bool(node.docker_status),
        needs_wireguard_setup=not bool(wireguard_target),
        needs_codex_setup=True,
        needs_node_token=False,
        last_heartbeat_at=node.last_heartbeat_at,
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


def serialize_image(image: ImageArtifact) -> ImageArtifactResponse:
    return ImageArtifactResponse(
        id=image.id,
        seller_user_id=image.seller_user_id,
        node_id=image.node_id,
        repository=image.repository,
        tag=image.tag,
        digest=image.digest,
        registry=image.registry,
        source_image=image.source_image,
        status=image.status,
        push_ready=image.status == "uploaded",
        created_at=image.created_at,
        updated_at=image.updated_at,
    )


def serialize_image_offer(offer: ImageOffer) -> ImageOfferResponse:
    return ImageOfferResponse(
        id=offer.id,
        seller_user_id=offer.seller_user_id,
        node_id=offer.node_id,
        image_artifact_id=offer.image_artifact_id,
        repository=offer.repository,
        tag=offer.tag,
        digest=offer.digest,
        runtime_image_ref=offer.runtime_image_ref,
        offer_status=offer.offer_status,
        probe_status=offer.probe_status,
        probe_measured_capabilities=offer.probe_measured_capabilities,
        pricing_error=offer.pricing_error,
        current_reference_price_cny_per_hour=offer.current_reference_price_cny_per_hour,
        current_billable_price_cny_per_hour=offer.current_billable_price_cny_per_hour,
        current_price_snapshot_id=offer.current_price_snapshot_id,
        last_probed_at=offer.last_probed_at,
        last_priced_at=offer.last_priced_at,
        pricing_stale_at=offer.pricing_stale_at,
        created_at=offer.created_at,
        updated_at=offer.updated_at,
    )


def serialize_node_token(node_token: NodeRegistrationToken) -> NodeTokenListResponse:
    return NodeTokenListResponse(
        id=node_token.id,
        label=node_token.label,
        expires_at=node_token.expires_at,
        revoked=node_token.revoked,
        used_node_key=node_token.used_node_key,
        last_used_at=node_token.last_used_at,
        created_at=node_token.created_at,
    )


def serialize_activity(event: ActivityEvent) -> ActivityEventResponse:
    return ActivityEventResponse(
        id=event.id,
        seller_user_id=event.seller_user_id,
        node_id=event.node_id,
        image_id=event.image_id,
        event_type=event.event_type,
        summary=event.summary,
        detail=event.detail,
        event_metadata=event.event_metadata,
        created_at=event.created_at,
    )
