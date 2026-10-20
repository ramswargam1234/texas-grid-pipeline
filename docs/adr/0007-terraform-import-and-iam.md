# ADR 0007: Terraform with import blocks; least-privilege IAM user

- **Status:** Accepted
- **Date:** 2026-10-19

## Context

The S3 bucket and pipeline IAM user were first created by hand in the console. They should be reproducible,
reviewable and hardened without being recreated (the bucket holds the lake).

## Decision

- Describe the bucket, its security settings and the IAM user/policy in `infra/terraform`, and adopt the
  existing resources with **`import` blocks** (`7 imported, 3 added, 3 changed, 0 destroyed`).
- Harden the bucket: public access blocked, ACLs disabled, SSE-S3 encryption, HTTPS-only bucket policy,
  versioning with 30-day expiry of old versions, `prevent_destroy`.
- The pipeline user may only list, read and write under `raw/` and `state/` in this one bucket. No delete.
- **Access keys are created in the console, not in Terraform**, so secrets never land in Terraform state.
- Terraform runs with a separate admin user whose key is deactivated between uses; state stays local and
  is never committed.

## Alternatives considered

| Option | Why not (for now) |
|---|---|
| Recreate everything from Terraform | Would mean migrating the lake; import is safer |
| Remote state (S3 + DynamoDB lock) | One maintainer; local state is acceptable. Needed for a team |

## Consequences

- Infrastructure changes are reviewed as code and applied from a saved plan.
- **Known weakness:** GitHub Actions authenticates with a **long-lived IAM access key** stored as a secret.
  The better design is **GitHub OIDC**: Actions assumes an IAM role with short-lived credentials and no
  stored key. Planned improvement.
