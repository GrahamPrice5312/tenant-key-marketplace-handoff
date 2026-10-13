from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from marketplace_handoff.infrai_client import InfraiClient, InfraiError
from marketplace_handoff.tenant_exchange import MarketplaceExchange, OrderHandoff, SellerAsset


class TenantSignup(BaseModel):
    tenant_id: str = Field(min_length=1)
    email: str = Field(min_length=3)
    name: str = Field(min_length=1)


class TenantKeyReceipt(BaseModel):
    tenant_id: str
    user_id: str
    key_id: str
    api_key: str
    notice: str = "Store this plaintext key now; it cannot be retrieved again."


class PurchaseRequest(BaseModel):
    buyer_tenant_id: str = Field(min_length=1)
    order_id: UUID


def create_app(infrai: InfraiClient | None = None) -> FastAPI:
    client = infrai or InfraiClient.from_environment()
    exchange = MarketplaceExchange(client)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        client.close()

    app = FastAPI(title="Tenant marketplace handoff", lifespan=lifespan)
    app.state.exchange = exchange

    @app.exception_handler(InfraiError)
    async def infrai_rejection(_: Any, exc: InfraiError) -> JSONResponse:
        client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        return JSONResponse(status_code=client_status, content={"detail": exc.detail})

    @app.post("/tenants", response_model=TenantKeyReceipt, status_code=201)
    def onboard_tenant(signup: TenantSignup) -> TenantKeyReceipt:
        credentials = exchange.onboard_tenant(
            tenant_id=signup.tenant_id,
            email=str(signup.email),
            name=signup.name,
        )
        return TenantKeyReceipt(tenant_id=signup.tenant_id, **credentials.__dict__)

    @app.post("/assets", response_model=SellerAsset, status_code=201)
    def publish_asset(asset: SellerAsset, x_tenant_key: str = Header()) -> SellerAsset:
        _require_tenant_key(exchange, asset.seller_tenant_id, x_tenant_key)
        return exchange.publish_asset(asset)

    @app.post("/assets/{asset_id}/orders", response_model=OrderHandoff)
    def handoff_order(
        asset_id: str, purchase: PurchaseRequest, x_tenant_key: str = Header()
    ) -> OrderHandoff:
        _require_tenant_key(exchange, purchase.buyer_tenant_id, x_tenant_key)
        return exchange.handoff_order(
            asset_id=asset_id,
            buyer_tenant_id=purchase.buyer_tenant_id,
            order_id=purchase.order_id,
        )

    @app.delete("/tenants/{tenant_id}", status_code=204)
    def offboard_tenant(tenant_id: str) -> None:
        exchange.offboard_tenant(tenant_id)

    return app


def _require_tenant_key(exchange: MarketplaceExchange, tenant_id: str, supplied: str) -> None:
    account = exchange._active_account(tenant_id)
    if exchange.key_digest(supplied) != account.key_digest:
        raise HTTPException(status_code=403, detail="tenant key does not match")


app = create_app()
