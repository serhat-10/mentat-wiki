# Security

## Reporting a vulnerability

Report privately through this repository's GitHub Security Advisories tab (`Security` ->
`Advisories` -> `New draft security advisory`).

Do not open a public issue with exploit details. Include the `mentat-wiki --version` output, your OS,
the command you ran, and the smallest reproduction. We will acknowledge the report and describe the
fix plan.

## In scope

- A privacy scan bypass that writes an API key, token, private key, secret assignment, home-folder
  path, or real email address into the vault. (RFC 2606 / `example.com` placeholders, version
  strings such as `react@18.2.0`, and `git@host:path` SSH remotes are intentionally allowed.)
- The installer or uninstaller changing settings or skills outside the entries it owns.
- Data loss from the vault lock or an atomic write.
- Code execution through hook or status-line stdin input.

## Out of scope

Symlinks or junctions you create inside your own vault are followed like any other folder.
Content you chose to store, third-party tools, and attacks that already require access to your
local user account or physical machine.
