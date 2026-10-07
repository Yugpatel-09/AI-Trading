# ADR 0002: User-Isolated Market Data Streams & Exchange Data Redistribution Compliance

## Status
Accepted

## Context
Under Indian exchange regulations (NSE and SEBI market data vending guidelines), streaming or redistributing real-time tick-level and market-depth data received through a broker's API (such as Zerodha Kite Connect) to other users or third parties constitutes unauthorized market data redistribution. Commercial redistribution of NSE tick data requires a formal Exchange Data Vendor license.

Furthermore, multi-user platforms that multiplex a single broker connection to stream prices across multiple traders risk severe regulatory penalties, breach of broker developer terms of service, and exchange IP blacklisting.

## Decision
1. **Strict User-Credential Isolation**: Each user must connect their own authenticated broker credentials (e.g. Kite Connect API key and session access token).
2. **Dedicated Ticker Stream**: When streaming real-time quotes or ticks, `KiteTickerProvider` instantiates a dedicated WebSocket connection using **only** that specific user's decrypted credentials from `crypto_vault`.
3. **No Cross-User Fan-Out**: The platform strictly prohibits fan-out or redistribution of market data ticks originating from User A's Kite connection to User B.
4. **Isolated Storage & Caching**: Live market data streams are processed in the user's private session scope. In multi-tenant environments, Redis channels and WebSocket pub/sub rooms are keyed per user (`user:{user_id}:ticks`).
5. **Session Expiry Enforcement**: Kite Connect tokens expire daily at ~06:00-07:30 IST. A daily pre-open session check is enforced at 09:00 IST to confirm the user's personal token validity before subscribing to market ticks.

## Consequences
- 100% compliance with NSE data vending norms and Zerodha Kite Connect developer terms.
- Zero liability regarding unlicensed data vendor classifications.
- Each user's quote streaming is strictly dependent on their own active broker subscription.
- No risk of one user's broker rate limits or disconnects degrading another user's algorithmic feed.
