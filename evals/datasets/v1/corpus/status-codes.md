# Status codes

The API uses standard HTTP status codes. A 200 response means the request succeeded. A 400 response means the request was malformed. A 401 response means the API key is missing or invalid. A 403 response means the key's role is not allowed to perform the action. A 404 response means the resource does not exist. A 429 response means the key exceeded its rate limit; wait for the number of seconds given in the Retry-After header. A 500 or 503 response means a problem on Helio's side and the request can be retried.
