# Team management

## Roles
Workspaces have four roles: Owner, Admin, Developer and Viewer. Owners control billing and can delete the workspace. Admins manage members and keys. Developers can create projects and use keys. Viewers have read-only access.

## Members and invitations
The number of members is limited by the plan: 1 on Free, 3 on Pro and 10 on Team, plus paid extra seats. Invitations expire after 7 days. A workspace has exactly one Owner, and ownership can be transferred to an Admin.

## API keys and members
API keys belong to the workspace, not to the person who created them. Removing a member does not revoke the keys they created, so admins should rotate keys when someone leaves.

## Audit log
Team and Enterprise workspaces have an audit log of sign-ins, key changes and member changes. Audit log entries are kept for 90 days.
