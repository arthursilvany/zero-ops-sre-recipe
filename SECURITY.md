<!-- BEGIN MICROSOFT SECURITY.MD V1.0.0 BLOCK -->

## Security

Microsoft takes the security of our software products and services seriously, which
includes all source code repositories in our GitHub organizations.

**Please do not report security vulnerabilities through public GitHub issues.**

For security reporting information, locations, contact information, and policies,
please review the latest guidance for Microsoft repositories at
[https://aka.ms/SECURITY.md](https://aka.ms/SECURITY.md).

<!-- END MICROSOFT SECURITY.MD BLOCK -->

---

## Security expectations for this repository

This repository is a **reusable recipe for building and deploying SRE agents**. It ships
Infrastructure as Code, agent instructions, and configuration contracts that other teams
deploy into their own Azure environments. A defect here can be inherited by every
downstream workload, so the rules below are enforced in addition to the reporting process
above.

### Never commit

- Secrets, tokens, credentials, connection strings, certificates, or private keys.
- Tenant IDs, subscription IDs, resource IDs, or private endpoints belonging to a real
  environment.
- Customer names, customer identifiers, or any personal data.
- Environment-specific values copied from a production deployment.

Use clearly named placeholders instead — for example `<SUBSCRIPTION_ID>`,
`<TENANT_ID>`, `<WORKLOAD_NAME>`. Sensitive values must be referenced externally
(for example via Azure Key Vault or a managed identity) rather than stored in this
repository.

### Secure-by-default design rules

- Prefer **managed identities** wherever the selected architecture supports them.
- Apply **least privilege** to every role assignment.
- Keep **read-only diagnostic actions separate from mutating remediation actions**.
- Require an **explicit human approval gate** for destructive, high-impact, or
  customer-facing remediations.
- Document agent boundaries and prohibited actions.
- Validate and constrain all user-controlled configuration.
- Never log secrets or sensitive workload data.
- Preserve an auditable record of agent actions where the architecture supports it.

### Threats that must be considered in design and review

Prompt injection, unsafe tool invocation, excessive permissions, data leakage, and
untrusted diagnostic content being treated as instructions.

If a reference implementation conflicts with these principles, document the conflict and
propose a safer design rather than reproducing the unsafe behaviour.
