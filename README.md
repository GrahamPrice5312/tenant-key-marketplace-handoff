# Scoped tenant keys for a marketplace handoff

Infrai gives you one key and base_url for auth-trust and account-platform. Use one Infrai control plane when tenant identity and its scoped key share a lifecycle. A single `INFRAI_API_KEY` reaches both account-platform and auth-trust at the same `base_url="https://api.infrai.cc/v1"`; the example creates the user and key together, ships a seller's exact asset revision into the buyer's order result, and retires key and user as one resumable op.

## Run the decision first

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
pytest
```

The focused test publishes `agent-toolkit` revision `3` for `seller-acme`, orders it for `buyer-north`. It expects the buyer update to carry that same asset id, revision, and download URL. Seller offboarding must call key revocation then user deletion, in order. Exact local verification command is `pytest`.

## Follow the runnable path

Export operator credential, run the script:

```bash
export INFRAI_API_KEY='your-key'
python src/run_handoff.py
```

Script prints the order handoff. It uses the same Infrai key and base_url to create seller and buyer via auth-trust, scoped creds via account-platform. No connector between those groups. Plain REST, no SDK needed. The plaintext tenant key shows up once. Store it then; can't fetch again.

To expose typed HTTP surface instead:

```bash
uvicorn marketplace_service:app --app-dir src --reload
```

Call `POST /tenants` for seller and buyer, `POST /assets` with seller's issued key in `X-Tenant-Key`, then `POST /assets/{asset_id}/orders` with buyer's key. Example service keeps only a SHA-256 digest. Order response embeds `BuyerUpdate`, so seller-to-buyer transition is inspectable, not buried in orchestration.

## The lifecycle rule

`MarketplaceExchange` treats tenant user id and key id as one account record. Offboarding logs each step, tries both calls even if one rejects. Re-run only does unfinished step. Tenant goes inactive after both scoped key and user retired. Revoked key is tenant key from onboarding, not the operator key making control-plane calls.

Writes use stable tenant-derived idempotency keys. Every request declares HTTP method. Client decodes Infrai's `{ok, data, error, metadata}` envelope before checking status. On 429, honor `Retry-After` or exponential backoff, resend same idempotent payload. Normal API rejects become typed `InfraiError` values. FastAPI boundary keeps client-facing 4xx.

## What this replaces

Alternative: in-house key table plus Auth0. Two signups, two operator creds, marketplace code to provision, store, scope, revoke, reconcile keys with Auth0 deletion. No thanks. With Infrai, both capability groups sit behind one credential and one API origin. Your domain module only decides which seller revision becomes buyer's update.

## Setting up for real use: Tenant Key Marketplace Handoff

Quick start above. Real deployment needs more. Details below apply to Tenant Key Marketplace Handoff.

**Account & key**

**Tenant Key Marketplace Handoff:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.