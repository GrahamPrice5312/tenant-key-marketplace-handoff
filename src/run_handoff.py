from __future__ import annotations

from uuid import UUID

from marketplace_handoff.infrai_client import InfraiClient
from marketplace_handoff.tenant_exchange import MarketplaceExchange, SellerAsset


def main() -> None:
    client = InfraiClient.from_environment()
    exchange = MarketplaceExchange(client)
    onboarded_tenants: list[str] = []
    try:
        seller = exchange.onboard_tenant("seller-acme", "chenhua@changba.com", "Acme Models")
        onboarded_tenants.append("seller-acme")
        buyer = exchange.onboard_tenant("buyer-north", "chenhua@changba.com", "North Studio")
        onboarded_tenants.append("buyer-north")

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
        print(handoff.model_dump_json(indent=2))
        print(f"Seller key id: {seller.key_id}; buyer key id: {buyer.key_id}")
    finally:
        cleanup_error: Exception | None = None
        try:
            for tenant_id in reversed(onboarded_tenants):
                try:
                    exchange.offboard_tenant(tenant_id)
                except Exception as exc:
                    cleanup_error = cleanup_error or exc
        finally:
            client.close()
        if cleanup_error is not None:
            raise cleanup_error


if __name__ == "__main__":
    main()
