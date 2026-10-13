from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .infrai_client import InfraiClient, TenantCredentials


TENANT_SCOPES = ["marketplace:assets", "marketplace:orders"]


class SellerAsset(BaseModel):
    asset_id: str = Field(min_length=1)
    seller_tenant_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    revision: int = Field(ge=1)
    download_url: str


class BuyerUpdate(BaseModel):
    asset_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    download_url: str


class OrderHandoff(BaseModel):
    order_id: UUID
    seller_tenant_id: str
    buyer_tenant_id: str
    update: BuyerUpdate


@dataclass
class TenantAccount:
    tenant_id: str
    user_id: str
    key_id: str
    key_digest: str
    active: bool = True
    retired_steps: set[str] = field(default_factory=set)


class MarketplaceExchange:
    """Keeps the business handoff visible while Infrai owns identity and scoped keys."""

    def __init__(self, infrai: InfraiClient) -> None:
        self.infrai = infrai
        self.accounts: dict[str, TenantAccount] = {}
        self.assets: dict[str, SellerAsset] = {}

    def onboard_tenant(self, tenant_id: str, email: str, name: str) -> TenantCredentials:
        user = self.infrai.create_user(
            email=email,
            name=name,
            metadata={"tenant_id": tenant_id, "role": "marketplace_tenant"},
            idempotency_key=f"tenant:{tenant_id}:user:v1",
        )
        try:
            key = self.infrai.create_key(
                project_id=tenant_id,
                name=f"tenant-{tenant_id}",
                scopes=TENANT_SCOPES,
                idempotency_key=f"tenant:{tenant_id}:key:v1",
            )
        except Exception:
            self.infrai.delete_user(str(user["id"]))
            raise
        credentials = TenantCredentials(
            user_id=str(user["id"]),
            key_id=str(key["id"]),
            api_key=str(key["key"]),
        )
        self.accounts[tenant_id] = TenantAccount(
            tenant_id=tenant_id,
            user_id=credentials.user_id,
            key_id=credentials.key_id,
            key_digest=self.key_digest(credentials.api_key),
        )
        return credentials

    def publish_asset(self, asset: SellerAsset) -> SellerAsset:
        account = self._active_account(asset.seller_tenant_id)
        if account.tenant_id != asset.seller_tenant_id:
            raise PermissionError("seller does not own this tenant")
        self.assets[asset.asset_id] = asset
        return asset

    def handoff_order(
        self, *, asset_id: str, buyer_tenant_id: str, order_id: UUID | None = None
    ) -> OrderHandoff:
        self._active_account(buyer_tenant_id)
        asset = self.assets[asset_id]
        self._active_account(asset.seller_tenant_id)
        return OrderHandoff(
            order_id=order_id or uuid4(),
            seller_tenant_id=asset.seller_tenant_id,
            buyer_tenant_id=buyer_tenant_id,
            update=BuyerUpdate(
                asset_id=asset.asset_id,
                revision=asset.revision,
                download_url=asset.download_url,
            ),
        )

    def offboard_tenant(self, tenant_id: str) -> TenantAccount:
        account = self.accounts[tenant_id]
        failures: list[Exception] = []

        if "key" not in account.retired_steps:
            try:
                self.infrai.revoke_key(account.key_id)
                account.retired_steps.add("key")
            except Exception as exc:
                failures.append(exc)

        if "user" not in account.retired_steps:
            try:
                self.infrai.delete_user(account.user_id)
                account.retired_steps.add("user")
            except Exception as exc:
                failures.append(exc)

        account.active = account.retired_steps != {"key", "user"}
        if failures:
            raise failures[0]
        return account

    @staticmethod
    def key_digest(api_key: str) -> str:
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    def _active_account(self, tenant_id: str) -> TenantAccount:
        account = self.accounts[tenant_id]
        if not account.active:
            raise PermissionError("tenant is offboarded")
        return account
