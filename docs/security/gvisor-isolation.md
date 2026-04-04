# gVisor Kernel-Level Isolation for RUNE UI

**Issue:** #12  
**Chart:** `charts/rune-ui`

---

## Overview

RUNE UI renders benchmark outputs (potentially untrusted LLM-generated HTML/text) inside a
Kubernetes pod.  To reduce the blast radius of any container escape, the pod can be scheduled onto
a node that runs the **gVisor** (`runsc`) container runtime, providing a user-space kernel
boundary between the container workload and the host Linux kernel.

This is a *deployment configuration scaffold* — the feature is **disabled by default** and must be
explicitly opted in per cluster.

---

## How It Works

```
┌──────────────────────────────────────────────┐
│  Kubernetes Node (Linux)                     │
│  ┌────────────────────────────────────────┐  │
│  │  gVisor (runsc)  ←  RuntimeClass       │  │
│  │  ┌──────────────────────────────────┐  │  │
│  │  │  RUNE UI Pod                     │  │  │
│  │  │  (untrusted benchmark output)    │  │  │
│  │  └──────────────────────────────────┘  │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

The `RuntimeClass` resource (`handler: runsc`) instructs the kubelet to hand container creation
to the `runsc` binary instead of `runc`.  When `runtimeClass.enabled: true`, the chart injects
`runtimeClassName: <name>` into the RUNE UI pod spec.

---

## Prerequisites

1. **gVisor installed on nodes** — follow the [gVisor installation guide](https://gvisor.dev/docs/user_guide/install/).
2. **Containerd configured** — `/etc/containerd/config.toml` must include the `runsc` runtime shim.
3. **Nodes tainted/labelled** (recommended) — label nodes that have gVisor available:
   ```bash
   kubectl label node <node-name> sandbox.gke.io/runtime=gvisor
   ```

---

## Enabling gVisor Isolation

In your `values.yaml` override:

```yaml
runtimeClass:
  enabled: true
  name: gvisor        # must match the RuntimeClass .metadata.name
```

Apply the chart:

```bash
helm upgrade --install rune-ui charts/rune-ui \
  --set runtimeClass.enabled=true \
  --set runtimeClass.name=gvisor
```

This will:
1. Create a `RuntimeClass` object named `gvisor` with `handler: runsc`.
2. Set `runtimeClassName: gvisor` on the RUNE UI `Deployment` pod spec.

---

## Disabling (Default)

```yaml
runtimeClass:
  enabled: false
```

When disabled, neither the `RuntimeClass` resource is created nor `runtimeClassName` is set on the
pod — the cluster default runtime (`runc`) is used.

---

## Security Considerations

| Aspect | Detail |
|--------|--------|
| Kernel isolation | gVisor interposes syscalls via a user-space kernel (`Sentry`), limiting direct host kernel exposure |
| Performance | ~10–30% overhead vs. `runc`; acceptable for UI workloads |
| Compatibility | Most Python/FastAPI workloads run unmodified under `runsc` |
| Not a silver bullet | gVisor does not protect against vulnerabilities within the container image itself |

---

## Kata Containers (Alternative)

If Kata Containers (`kata-qemu`) is preferred over gVisor, change `handler`:

```yaml
runtimeClass:
  enabled: true
  name: kata
  handler: kata-qemu
```

And update `charts/rune-ui/templates/runtime-class.yaml` to use a configurable `handler` field.

---

## References

- [gVisor Documentation](https://gvisor.dev/docs/)
- [Kubernetes RuntimeClass](https://kubernetes.io/docs/concepts/containers/runtime-class/)
- [containerd gVisor integration](https://github.com/google/gvisor/blob/master/g3doc/user_guide/containerd/quick_start.md)
