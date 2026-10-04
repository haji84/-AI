# Windows server profile

This profile is a fallback when the approved LAN server is Windows.

- Client PCs do not run this script. They only use a browser.
- Store secrets in `C:\FireAI\backend\.env` with ACL restricted to the service account.
- Run the API under a dedicated non-administrator service account.
- Prefer an organization-approved reverse proxy/TLS endpoint in front of port 8080.
- Restrict Windows Firewall so only the internal LAN/reverse proxy can reach the service.
- Do not map the PostgreSQL port broadly to client PCs.
- The operational shared folder should be writable by the server service account, not by every client if avoidable.

`start-fire-ai.cmd` is a smoke-test launcher, not the final service registration mechanism. Use the organization's approved Windows service/task mechanism for automatic startup.