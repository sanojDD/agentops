# Webhooks

## Delivery
Helio sends webhook events as HTTP POST requests with a JSON body. An endpoint must answer with a 2xx status within 10 seconds, otherwise the delivery counts as failed. The maximum webhook payload is 256 KB.

## Retries
Failed deliveries are retried 5 times with exponential backoff, over a period of up to 24 hours. After the fifth failure the event is marked as undelivered and the endpoint is flagged in the dashboard. Undelivered events can be replayed manually for 7 days.

## Verifying signatures
Every request carries a Helio-Signature header containing an HMAC-SHA256 signature of the body, computed with the endpoint's signing secret. Receivers should reject requests whose signature does not match. Signing secrets can be rotated without downtime.

## Event types
Available events include project.created, project.deleted, invoice.paid and key.revoked.
