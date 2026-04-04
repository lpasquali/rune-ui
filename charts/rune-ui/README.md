# rune-ui Helm Chart

Deploys the **RUNE UI** web front-end to a Kubernetes cluster.

## Quick Start

```bash
helm install rune-ui charts/rune-ui \
  --set env.RUNE_API_URL=http://rune-api.default.svc.cluster.local:8080
```

## Values

| Key | Default | Description |
|-----|---------|-------------|
| `replicaCount` | `1` | Number of UI replicas |
| `image.repository` | `ghcr.io/lpasquali/rune-ui` | Container image |
| `image.tag` | `""` (uses appVersion) | Image tag |
| `service.type` | `ClusterIP` | Kubernetes service type |
| `service.port` | `8080` | Service port |
| `env.RUNE_API_URL` | `http://rune-api…:8080` | RUNE core API URL |
| `runtimeClass.enabled` | `false` | Enable gVisor/Kata kernel isolation |
| `runtimeClass.name` | `gvisor` | RuntimeClass name to apply to the pod |
| `runtimeClass.handler` | `runsc` | Low-level runtime handler (containerd) |

## gVisor / Kata Kernel Isolation (Issue #12)

To run RUNE UI inside a sandboxed kernel runtime (gVisor):

```bash
helm upgrade --install rune-ui charts/rune-ui \
  --set runtimeClass.enabled=true \
  --set runtimeClass.name=gvisor \
  --set runtimeClass.handler=runsc
```

This creates a `RuntimeClass` named `gvisor` and sets `runtimeClassName: gvisor` on the pod spec,
routing all containers through the `runsc` (gVisor) runtime instead of `runc`.

**Prerequisites:** gVisor must be installed on the target nodes and registered with containerd.
See [`docs/security/gvisor-isolation.md`](../../docs/security/gvisor-isolation.md) for full setup
instructions.
