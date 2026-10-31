# Shared research service contracts

Internal in-process contracts for the developing full VirtualLab desktop/web/ChatGPT integration. The service report and access-policy schemas also freeze the first private read-only transport boundary. These schemas do not define a public unauthenticated API. The policy is operator-owned configuration, never a client-provided grant.

See [HTTP operations, authentication, verification and remaining integration gates](../../docs/read-only-research-service.md). Re-export/check service schemas with `python -m scripts.export_research_service_contract --check`.

See [engine implementation and integration limits](../../docs/shared-research-engine.md). The existing hosted web adaptation remains under its current development and access controls. No website deployment occurred here.
