"""Real Kubernetes execution driver.

Performs live remediation against a cluster via the official Kubernetes client.
It runs only when ``EXECUTION_BACKEND=kubernetes`` — the mock driver is the
default so nothing destructive happens by accident.

Safety posture (defence in depth, on top of the contract guardrails):
- Every action is scoped to a single namespace + deployment (``target``).
- ``restart_pods`` performs a rolling restart via a template annotation (the
  standard ``kubectl rollout restart`` mechanism) rather than blind pod deletes,
  so the Deployment controller preserves availability.
- ``rollback_deployment`` uses the Deployment's rollout history.
- Read operations (status/metrics) are derived from live ReplicaSet/Pod state.

Config maps to ``kubernetes.config``: in-cluster service account when
``K8S_IN_CLUSTER=true``, otherwise a kubeconfig (default resolution or an
explicit path).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from core.execution.drivers.base import ExecutionDriver

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class KubernetesDriver(ExecutionDriver):
    def __init__(
        self,
        namespace: str = "default",
        in_cluster: bool = False,
        kubeconfig: str | None = None,
    ) -> None:
        from kubernetes import client, config

        try:
            if in_cluster:
                config.load_incluster_config()
            elif kubeconfig:
                config.load_kube_config(config_file=kubeconfig)
            else:
                config.load_kube_config()
        except Exception as exc:  # pragma: no cover - environment-specific
            raise RuntimeError(f"Failed to load Kubernetes config: {exc}") from exc

        self.namespace = namespace
        self._apps = client.AppsV1Api()
        self._core = client.CoreV1Api()
        logger.info("KubernetesDriver ready (namespace=%s, in_cluster=%s)", namespace, in_cluster)

    # ------------------------------------------------------------------
    def execute(self, action: str, target: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if action == "restart_pods":
            return self.restart_pods(target, int(parameters.get("count", 1)))
        if action == "scale_deployment":
            return self.scale_deployment(target, int(parameters.get("replicas", 1)))
        if action == "rollback_deployment":
            return self.rollback_deployment(target, int(parameters.get("revision", 1)))
        return {"success": False, "error": f"Unknown action: {action}"}

    def _label_selector(self, deployment: str) -> str:
        # Convention: pods are labelled app=<deployment>. Adjust per-cluster.
        return f"app={deployment}"

    def restart_pods(self, deployment: str, count: int) -> dict[str, Any]:
        """Trigger a rolling restart of the deployment.

        `count` is advisory here — a Deployment rolling restart is the safe
        primitive (the controller respects maxUnavailable). We record it for the
        audit trail. Guardrails have already bounded `count`.
        """
        from kubernetes.client.rest import ApiException

        try:
            patch = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "gaap.restartedAt": _now(),
                                "gaap.restartReason": "contract-bound-remediation",
                            }
                        }
                    }
                }
            }
            self._apps.patch_namespaced_deployment(
                name=deployment, namespace=self.namespace, body=patch
            )
            return {
                "action": "restart_pods",
                "deployment": deployment,
                "namespace": self.namespace,
                "restart_count": count,
                "method": "rolling_restart",
                "success": True,
                "timestamp": _now(),
            }
        except ApiException as exc:
            return self._error("restart_pods", deployment, exc)

    def scale_deployment(self, deployment: str, replicas: int) -> dict[str, Any]:
        from kubernetes.client.rest import ApiException

        try:
            current = self._apps.read_namespaced_deployment_scale(
                name=deployment, namespace=self.namespace
            )
            previous = current.spec.replicas
            body = {"spec": {"replicas": replicas}}
            self._apps.patch_namespaced_deployment_scale(
                name=deployment, namespace=self.namespace, body=body
            )
            return {
                "action": "scale_deployment",
                "deployment": deployment,
                "namespace": self.namespace,
                "previous_count": previous,
                "new_count": replicas,
                "success": True,
                "timestamp": _now(),
            }
        except ApiException as exc:
            return self._error("scale_deployment", deployment, exc)

    def rollback_deployment(self, deployment: str, revision: int) -> dict[str, Any]:
        """Roll back to the previous known-good ReplicaSet.

        Kubernetes removed the Deployment ``rollback`` subresource, so we
        emulate ``kubectl rollout undo`` by re-applying the pod template of the
        target (or immediately-previous) ReplicaSet.
        """
        from kubernetes.client.rest import ApiException

        try:
            rs_list = self._apps.list_namespaced_replica_set(
                namespace=self.namespace, label_selector=self._label_selector(deployment)
            )
            revisions = sorted(
                rs_list.items,
                key=lambda rs: int(
                    rs.metadata.annotations.get("deployment.kubernetes.io/revision", "0")
                ),
            )
            if len(revisions) < 2:
                return {
                    "action": "rollback_deployment",
                    "deployment": deployment,
                    "error": "No previous revision available to roll back to",
                    "success": False,
                    "timestamp": _now(),
                }
            target_rs = revisions[-2]  # immediately previous
            template = target_rs.spec.template
            self._apps.patch_namespaced_deployment(
                name=deployment,
                namespace=self.namespace,
                body={"spec": {"template": template.to_dict()}},
            )
            return {
                "action": "rollback_deployment",
                "deployment": deployment,
                "namespace": self.namespace,
                "rolled_back_to_revision": target_rs.metadata.annotations.get(
                    "deployment.kubernetes.io/revision"
                ),
                "success": True,
                "timestamp": _now(),
            }
        except ApiException as exc:
            return self._error("rollback_deployment", deployment, exc)

    def get_service_status(self, service: str) -> dict[str, Any]:
        from kubernetes.client.rest import ApiException

        try:
            pods = self._core.list_namespaced_pod(
                namespace=self.namespace, label_selector=self._label_selector(service)
            )
            pod_list = []
            healthy = 0
            for p in pods.items:
                ready = any(
                    c.type == "Ready" and c.status == "True"
                    for c in (p.status.conditions or [])
                )
                healthy += 1 if ready else 0
                pod_list.append({"name": p.metadata.name, "status": "healthy" if ready else "unhealthy"})
            return {
                "action": "get_service_status",
                "service": service,
                "total_pods": len(pod_list),
                "healthy_pods": healthy,
                "unhealthy_pods": len(pod_list) - healthy,
                "pods": pod_list,
                "success": True,
                "timestamp": _now(),
            }
        except ApiException as exc:
            return self._error("get_service_status", service, exc)

    def get_metrics(self, service: str) -> dict[str, Any]:
        status = self.get_service_status(service)
        if not status.get("success"):
            return {**status, "action": "get_metrics"}
        total = status["total_pods"]
        healthy = status["healthy_pods"]
        # Without a metrics backend we derive an availability-based error proxy.
        error_rate = round((1 - (healthy / total)) * 100, 2) if total else 100.0
        return {
            "action": "get_metrics",
            "service": service,
            "error_rate": error_rate,
            "healthy_pods": healthy,
            "total_pods": total,
            "success": True,
            "timestamp": _now(),
        }

    @staticmethod
    def _error(action: str, target: str, exc: Exception) -> dict[str, Any]:
        logger.error("Kubernetes %s on %s failed: %s", action, target, exc)
        return {
            "action": action,
            "deployment": target,
            "error": str(exc),
            "success": False,
            "timestamp": _now(),
        }
