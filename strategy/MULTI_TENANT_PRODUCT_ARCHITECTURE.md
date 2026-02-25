# Multi-Tenant Product Architecture (Internal)

## Goal

Keep the **customer-facing Flair experience** fully Flair-branded while making the platform easy to refactor for:

- other airlines (especially low-cost and regional carriers)
- intercity bus operators
- ferry operators
- other travel businesses with disruptions, changes, refunds, and multi-channel support demand

## What Was Implemented

### 1. Tenant Profiles

Tenant profiles are now stored in:

- `tenants/profiles/flair.json`
- `tenants/profiles/airline_template.json`
- `tenants/profiles/intercity_bus_template.json`

These profiles control:

- display name / branding labels
- supported channels
- customer-facing capabilities text
- support commitments text
- intent -> citation topic mapping
- intent -> self-service options mapping

### 2. Tenant Registry

- `tenants/registry.py`

Provides:

- `TenantRegistry.load(slug)`
- `TenantRegistry.try_load(slug)`
- `TenantRegistry.list_profiles()`

### 3. Tenant Knowledge Tools

- `tools/tenant_knowledge_tools.py`

Generic knowledge layer that loads:

- tenant profile
- tenant public support snapshot
- intent-specific citations
- official channel summaries
- self-service options

### 4. Flair Knowledge Tools (Backward-Compatible)

- `tools/flair_knowledge_tools.py`

Now a thin subclass of the generic tenant knowledge tools using Flair defaults.

### 5. Tenant Orchestrator Pool

- `api/tenant_pool.py`

Caches an `OrchestratorAgent` per tenant slug for white-label reuse without changing the core code.

### 6. Hidden Tenant Support in Customer API

Customer endpoints accept tenant selection (defaults to `flair`) via:

- payload `tenant`
- `X-Tenant` header
- `?tenant=` query param

The visible `/support` route remains Flair by default.

## Why This Refactor Matters

It separates:

- **core support orchestration engine**
- **tenant-specific knowledge + channels + self-service mapping**
- **customer-facing brand text**

This means the system can be reused for similar businesses by replacing:

- tenant profile JSON
- public support knowledge snapshot JSON
- (optionally) domain-specific agent/tool extensions

instead of rewriting the entire product.

## Next Refactor Steps For Easier Vertical Expansion

1. Move more airline-specific wording out of agent classes and into tenant/domain policy prompts
2. Add domain plugins (airline, bus, ferry) for intent-specific edge cases
3. Replace mock tools with tenant-specific adapters (booking, CRM, ops status)
4. Add tenant-scoped persistence (Redis/Postgres namespaces)

