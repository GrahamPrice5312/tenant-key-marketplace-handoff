from uuid import UUID

import pytest

from marketplace_handoff.infrai_client import TenantCredentials
from marketplace_handoff.tenant_exchange import MarketplaceExchange, SellerAsset


class RecordingInfrai:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def create_user(self, **values: object) -> dict[str, str]:
        tenant_id = str(values["metadata"]["tenant_id"])  # type: ignore[index]
        return {"id": f"user-{tenant_id}"}

    def create_key(self, **values: object) -> dict[str, str]:
        project_id = str(values["project_id"])
        return {"id": f"key-{project_id}", "key": f"issued-{project_id}"}

    def revoke_key(self, key_id: str) -> dict[str, bool]:
        self.calls.append(("revoke_key", key_id))
        return {"revoked": True}

    def delete_user(self, user_id: str) -> dict[str, bool]:
        self.calls.append(("delete_user", user_id))
        return {"deleted": True}


class KeyCreationFailureInfrai(RecordingInfrai):
    def create_key(self, **values: object) -> dict[str, str]:
        raise RuntimeError("key creation failed")


def test_onboarding_deletes_user_when_key_creation_fails() -> None:
    infrai = KeyCreationFailureInfrai()
    exchange = MarketplaceExchange(infrai)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="key creation failed"):
        exchange.onboard_tenant("seller-acme", "chenhua@changba.com", "Acme Models")

    assert infrai.calls == [("delete_user", "user-seller-acme")]
    assert exchange.accounts == {}


def test_order_moves_seller_revision_to_buyer_and_offboarding_retires_both() -> None:
    infrai = RecordingInfrai()
    exchange = MarketplaceExchange(infrai)  # type: ignore[arg-type]
    seller: TenantCredentials = exchange.onboard_tenant(
        "seller-acme", "seller@example.com", "Acme Models"
    )
    exchange.onboard_tenant("buyer-north", "buyer@example.com", "North Studio")
    exchange.publish_asset(
        SellerAsset(
            asset_id="agent-toolkit",
            seller_tenant_id="seller-acme",
            title="Agent tool bundle",
            revision=3,
            download_url="https://downloads.example.com/agent-toolkit-r3.zip",
        )
    )

    handoff = exchange.handoff_order(
        asset_id="agent-toolkit",
        buyer_tenant_id="buyer-north",
        order_id=UUID("8a4ff572-1b62-4c84-9808-c676b5ae81ea"),
    )
    retired = exchange.offboard_tenant("seller-acme")

    assert handoff.update.model_dump() == {
        "asset_id": "agent-toolkit",
        "revision": 3,
        "download_url": "https://downloads.example.com/agent-toolkit-r3.zip",
    }
    assert seller.key_id == "key-seller-acme"
    assert infrai.calls == [
        ("revoke_key", "key-seller-acme"),
        ("delete_user", "user-seller-acme"),
    ]
    assert retired.active is False
