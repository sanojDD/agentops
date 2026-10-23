# Authentication and access

## API keys
Every API key starts with the prefix hk_live_ for production or hk_test_ for the sandbox. Keys are shown only once when they are created. Helio recommends rotating keys every 90 days. A key can be revoked at any time from the workspace settings, and revoked keys stop working within 60 seconds.

## OAuth
Integrations that act on behalf of users should use OAuth 2.0. Access tokens expire after 1 hour. Refresh tokens expire after 30 days of inactivity.

## Two-factor authentication
Two-factor authentication with an authenticator app is mandatory for workspace owners and admins. SMS codes are not supported.

## Single sign-on
SAML single sign-on is available on the Enterprise plan. When single sign-on is enabled, members can no longer sign in with a password.
