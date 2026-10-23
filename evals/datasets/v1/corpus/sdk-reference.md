# SDK reference

## Overview
Helio provides SDKs that wrap the REST API and add convenience features such as automatic pagination and typed responses.

## Creating a client
In JavaScript, create a client with new Helio({ apiKey }). In Python, use Helio(api_key=...). If no key is passed, the SDK reads the HELIO_API_KEY environment variable.

## Automatic retries
The SDKs retry requests that fail with status 429 or 503. By default a request is attempted up to 4 times, with a short pause that grows after every attempt. Retries can be switched off with the max_retries option.

## Timeouts
The default timeout of an SDK request is 30 seconds. Long running exports should use the asynchronous export endpoint instead.

## Versions
SDK releases follow semantic versioning. Breaking changes only happen in major versions.
