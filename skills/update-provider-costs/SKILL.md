---
name: update-provider-costs
description: Update AI provider pricing in the providers database table from current official pricing sources. Use when asked to refresh costs, pricing, or token rates for OpenAI/Grok/Claude/Gemini and write them into db/report_overrides.db.
---

# Update Provider Costs

Use this skill to refresh provider pricing (input/output $ per 1M tokens) in the database.

## Workflow

1. Use `web.run` to fetch **official pricing pages** for the providers referenced in `providers` table.
2. Extract the **current** input/output $ per 1M tokens for the specific models in use.
3. Update the DB via the script below.

## Script

Update one provider:

```powershell
python scripts\update_provider_costs.py --provider openai --input 0.15 --output 0.60
```

Update multiple providers in one run:

```powershell
python scripts\update_provider_costs.py --json '{"openai":{"input":0.15,"output":0.60},"claude":{"input":3.0,"output":15.0}}'
```

## Notes

- Only update providers that exist in the DB.
- Do **not** delete providers if missing from config.
- Always cite sources used for pricing in the response.
