# TradeForge Shared Package (`packages/shared`)

Single source of truth for domain models, enums, schemas, and statutory formulas used across Python microservices and the TypeScript frontend.

## Structure
- `python/tradeforge_shared/`:
  - `enums.py`: Order sides, order types, strategy types, market regimes, trading modes.
  - `schemas.py`: Pydantic v2 data models for candles, signals, orders, positions, and risk settings.
  - `costs.py`: Statutory Indian transaction cost calculation engine.
- `ts/`:
  - `index.ts`: TypeScript interfaces and types synchronized with the Python models.
