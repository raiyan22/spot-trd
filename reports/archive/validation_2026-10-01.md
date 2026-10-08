# Validation (2026-10-01): PASS: System healthy

| Check | Status | Detail |
|---|---|---|
| BTC data fresh | PASS | last daily close 2026-09-30 |
| Macro data fresh | PASS | latest macro row is 0 day(s) old (weekends and US holidays allow up to 4) |
| Latest features complete | PASS | all decision inputs present |
| Price sanity | PASS | last daily move -0.0% |
| Event calendar coverage | PASS | FOMC/CPI dates known through 2026-12-10 (CPI) |
| Binance limits match config | PASS | min order, lot step and fee unchanged |
| Recent 12 months (backtest) | INFO | only 1 trades in the last year; too few to judge |
| Live vs backtest | INFO | no closed trades yet; checks start after the first exit |