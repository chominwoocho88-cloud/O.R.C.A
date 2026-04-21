# Research Gate Result

- Generated: `2026-04-21T13:53:38.199686+09:00`
- Source report generated: `2026-04-21T13:53:38.036358+09:00`
- Overall status: `fail`
- Fail count: `1`
- Warn count: `7`

## Checks

| Check | Status | Current | Delta | Threshold | Reason |
| --- | --- | ---: | ---: | ---: | --- |
| orca_final_accuracy_delta | pass | 58.7 | +0.0 | -5.0 | ok |
| jackal_swing_accuracy_delta | warn | n/a | n/a | -5.0 | insufficient_history |
| jackal_d1_accuracy_delta | warn | n/a | n/a | -5.0 | insufficient_history |
| jackal_shadow_rolling_10_rate | warn | 0.0 | n/a | 45.0 | insufficient_history |
| jackal_linked_to_latest_orca | fail | False | n/a | n/a | mismatch |

## Report Warnings

- No JACKAL shadow batch history recorded yet.
- No SQL-projected JACKAL swing signal accuracy snapshot with enough samples yet.
- No SQL-projected JACKAL ticker accuracy snapshot with enough samples yet.
- No SQL-projected JACKAL recommendation regime accuracy snapshot with enough samples yet.
