# TradeForge Machine Learning (`ml/`)

Houses machine learning research, walk-forward training pipelines, model registries, and drift monitoring.

## Safety Constraint
The ML quality models are **strictly filtering gates**. They output a probability score representing the historical likelihood that a candidate setup will reach target before hitting stop.
- A model may **reject** or **pass** a signal.
- A model may **never** fabricate trades on its own or override the Risk Guard.
