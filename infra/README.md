# DynamicRunner infra

Infrastructure/config folder for deployment and environments.

## POC target (current)

- Docker: [`backend/Dockerfile`](../backend/Dockerfile)
- Deploy guide: [`DEPLOY.md`](DEPLOY.md) (Render deploy hook + env vars)
- Blueprint: [`render.yaml`](render.yaml)
- CI: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)

## Future AWS migration

When moving off POC hosting, this folder will also contain Terraform and AWS modules (`[future-aws]` items in `TODO.md`).

