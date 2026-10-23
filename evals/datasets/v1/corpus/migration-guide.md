# Migrating from API version 1

## Overview
Version 2 of the API replaces version 1. Both versions run in parallel, and requests to version 1 keep working during the migration period.

## What changed
Endpoints now use plural resource names, for example /v2/projects instead of /v1/project. Errors return a JSON body with a code and a message. Pagination uses cursors instead of page numbers.

## Rate limits
Rate limits are the same for both versions and are counted together per API key.

## Checklist
Update the SDK to the latest version, switch the base URL to /v2, and run your integration tests against the sandbox before moving production traffic.
