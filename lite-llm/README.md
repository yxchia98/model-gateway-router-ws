# LiteLLM gateway

Single-host gateway with no preset models or routes. Add providers, models,
virtual keys and routing configurations in the Admin UI. Model definitions and
credentials are stored in PostgreSQL with `STORE_MODEL_IN_DB=True`.

The stack includes LiteLLM, PostgreSQL, Redis routing state, and optional
Prometheus/Grafana monitoring. Named volumes persist data, services restart
automatically, and container logs rotate at 10 MB with three files per container.

## Start the gateway

```bash
cd /home/ubuntu/code/model-gateway-router-ws/lite-llm
docker compose config --quiet
docker compose up -d --wait --wait-timeout 300
# To include Prometheus and Grafana:
docker compose --profile monitoring up -d --wait --wait-timeout 300
```

The private, Git-ignored `.env` contains generated local credentials and has
mode 0600. Provider API keys are optional at startup. A fresh clone should copy
`.env.example` to `.env` and replace all secret placeholders with random values
(`openssl rand -hex 32`; prefix LiteLLM master/salt keys with `sk-`).

Open http://localhost:4000/ui and sign in with `UI_USERNAME` and `UI_PASSWORD`
from `.env`. In **Models + Endpoints**, add your chosen provider and model,
configure credentials, and test the connection. Add routing configurations only
after their target models exist. Create virtual keys for applications and use
the model names you define in the UI at `http://localhost:4000/v1`.

`config.yaml` intentionally has `model_list: []`. A new database starts without
models. Existing UI/database model definitions remain available after restarting;
removing YAML presets does not delete records already saved in PostgreSQL.
Remove any unwanted existing models/routes through the UI.

## Optional provider credentials and Jev routing

You can enter credentials directly in the UI, or set `OPENAI_API_KEY` and
`OPENROUTER_API_KEY` in `.env` and reference them in the UI API key field as
`os.environ/OPENAI_API_KEY` or `os.environ/OPENROUTER_API_KEY`. The Compose service
passes these variables to LiteLLM. OpenRouter deployments use LiteLLM model IDs
of the form `openrouter/<OpenRouter model ID>`.

To configure Jev routing later, set `TYPESAFE_API_KEY` in `.env`, recreate the
gateway, and configure an Auto Router in the UI using Jev and your deployed
models as tier targets. No Jev router is preconfigured. Jev classification uses
TypeSafe's hosted API and sends the configured classification context there.

```bash
# Apply environment changes:
docker compose up -d --force-recreate litellm
```

## Access and monitoring

| Interface | URL | Credentials |
| --- | --- | --- |
| Admin UI | http://localhost:4000/ui | UI_USERNAME / UI_PASSWORD |
| API | http://localhost:4000/v1 | Virtual key created in the UI |
| Prometheus (monitoring profile) | http://localhost:9090 | Local access |
| Grafana (monitoring profile) | http://localhost:3000 | GRAFANA_ADMIN_USER / GRAFANA_ADMIN_PASSWORD |

Grafana has a provisioned Prometheus datasource. Create/import dashboards in its
UI; they persist in its named volume. Confirm the LiteLLM target is UP at
Prometheus `/targets`. The dedicated metrics listener is private on port 4001.
Redis shares routing state; completion response caching is disabled.

The gateway binds to `0.0.0.0` by default and is reachable at `http://<host-ip>:4000`. Prometheus and Grafana also bind to `0.0.0.0`, on ports 9090 and 3000 when the monitoring profile is enabled. PostgreSQL and Redis have no host
ports. For access from another computer:

```bash
ssh -L 4000:127.0.0.1:4000 -L 3000:127.0.0.1:3000 ubuntu@EM-MY-2
```

Use an authenticated TLS reverse proxy before publishing the gateway publicly.
This Compose stack is a single-host deployment, not a highly available cluster.

## Health and operations

```bash
docker compose ps
curl --fail-with-body http://localhost:4000/health/readiness
docker compose logs --tail=100 litellm
# Stop while preserving data:
docker compose --profile monitoring down
# Database backup:
mkdir -p backups
chmod 700 backups
docker compose exec -T postgres pg_dump -U litellm -d litellm -Fc > backups/litellm.dump
chmod 600 backups/litellm.dump
```

Keep an encrypted/off-host copy of `.env` alongside database backups. Preserve
`LITELLM_SALT_KEY`: changing it makes stored provider credentials unreadable.
Changing `POSTGRES_PASSWORD` in `.env` does not rotate an existing database role;
update the role and environment together. Grafana's initial admin password also
only applies on first database creation. `docker compose down -v` deletes data.

LiteLLM is pinned by image digest; supporting services use version tags. Back up
data before upgrading and validate migrations and any UI-created routing rules.
Compose and static configuration checks have passed; runtime/provider validation
has not been performed as part of this configuration change.

## References

- [LiteLLM Docker quickstart and UI model management](https://docs.litellm.ai/docs/proxy/docker_quick_start)
- [LiteLLM Auto Routing and Jev](https://docs.litellm.ai/docs/proxy/auto_routing)
- [LiteLLM OpenRouter provider](https://docs.litellm.ai/docs/providers/openrouter)
- [LiteLLM Prometheus metrics](https://docs.litellm.ai/docs/proxy/prometheus)
