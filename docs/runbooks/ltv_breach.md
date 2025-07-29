# LTV Breach Runbook

This runbook describes how to investigate and mitigate situations where the loan-to-value (LTV) ratio exceeds 80%.

## Investigation steps
1. **Grafana:** Check the `HighLTVRatio` alert and inspect related dashboards for sudden spikes.
2. **Aggregator logs:** Review logs from the asset aggregator service for any anomalous asset valuations.
3. **CreditFacility draw/repay history:** Confirm recent draws or repayments on the credit facility that may have impacted the ratio.

## Mitigation
* Perform a manual repayment to bring the LTV ratio below the limit.
* Increase posted collateral if repayment is not immediately possible.
