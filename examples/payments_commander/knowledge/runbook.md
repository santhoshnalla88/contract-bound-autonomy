# Payments Domain Runbooks

## High Decline Rate Anomaly
If the `decline_rate` exceeds 10% and `latency_ms` exceeds 1000ms:
1. Reroute gateway traffic away from the affected gateway.
   - Action: `reroute_gateway`
   - Parameters: `{"gateway": "backup_gateway"}`
2. Ensure you check for PCI compliance implications.

## Merchant Fraud Spike
If chargebacks or anomalous transactions are detected for a specific merchant:
1. Block the merchant immediately to prevent further exposure.
   - Action: `block_merchant`
   - Parameters: `{"merchant_id": "<target_merchant>"}`
2. Refund recent fraudulent transactions.
   - Action: `refund_transaction`
   - Parameters: `{"transaction_id": "<target_transaction>"}`
