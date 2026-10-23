# API rate limits

## Limits per plan
Rate limits are applied per API key. The Free plan allows 60 requests per minute, Pro allows 600, and Team allows 3000 requests per minute. Enterprise limits are agreed in the contract.

## Bursts
Every key may burst to twice its limit for up to 10 seconds. After that, requests above the limit are rejected.

## What happens when the limit is exceeded
Requests above the limit receive HTTP status 429 and a Retry-After header that tells the client how many seconds to wait. Clients should back off and retry after that time instead of retrying immediately.

## Request size
The maximum request payload is 5 MB. The batch endpoint accepts at most 100 items per call. Responses larger than 10 MB are paginated.

## Concurrency
Each API key can have at most 20 requests in flight at the same time on Free and Pro, and 100 on Team.
