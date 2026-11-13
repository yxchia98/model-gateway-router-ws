# model-gateway-router-ws

## Linked repositories

[Switchyard](https://github.com/NVIDIA-NeMo/Switchyard/tree/v0.4.0a1) is included
as the `switchyard/` Git submodule, pinned to tag `v0.4.0a1`
(commit `33cc0b864b5de8c76e9d203898273718155e4b2f`).

After cloning this repository, initialize it with:

```bash
git submodule update --init --recursive
```

## Standalone deployments

- [LiteLLM gateway](lite-llm/README.md): add models and routes in its Admin UI.
- [NeMo Switchyard](nemo-switchyard/README.md): System One decisions and free OpenRouter completion targets.

- [Routing playground](nemo-switchyard/frontend/README.md): interactive frontend for the standalone Switchyard gateway (localhost:3002).
