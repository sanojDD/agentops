# Security overview

## Application security
Helio performs an external penetration test once a year and fixes critical findings within 14 days. Dependencies are scanned for known vulnerabilities on every build.

## Key handling
API keys are stored only as salted hashes, which is why a key cannot be displayed again after creation. Keys can be restricted to a list of IP addresses on the Team and Enterprise plans.

## Infrastructure
Production systems run in isolated networks, and access for Helio staff requires hardware security keys. Administrative actions by staff are logged and reviewed every month.

## Vulnerability disclosure
Security researchers are welcome to report vulnerabilities to the security team. Reports are triaged by severity, and confirmed issues are fixed in order of risk.
