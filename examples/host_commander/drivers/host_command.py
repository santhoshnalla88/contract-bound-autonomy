"""Reference execution driver for NON-Kubernetes targets.

This is the template for integrating the platform with the rest of the world:
Linux / Windows servers, VMs, bare metal, on-prem application hosts, batch /
scheduler systems, and cloud / SaaS REST APIs. It shows the two transports that
cover almost everything:

* **command transport** — run a *pre-approved* command on a host. Transport is
  pluggable: ``local`` (subprocess, this box), ``ssh`` (remote Linux — paramiko),
  ``winrm`` (remote Windows — pywinrm). Maps the ``run_command`` /
  ``restart_service`` / ``start_service`` / ``stop_service`` / ``run_batch_job``
  verbs to command *templates* you define.
* **http transport** — the ``http_request`` verb, for cloud/SaaS APIs and webhooks.

Safety model (why this is ops-automation, not "let the LLM run shell"):
the driver NEVER executes free-form model text. It only runs commands from the
``commands`` allowlist you pass in, and every parameter is shell-quoted before
substitution. The model can pick an *allowlisted action* and supply *parameters*
— nothing else. This is the same posture as Ansible / SSM runbooks, and it sits
*behind* the contract, policy, risk, approval, and audit gates.

Wire it up in your app/worker startup::

    from core.execution.drivers import register_driver
    from examples.host_commander.drivers.host_command import HostCommandDriver

    register_driver("host", lambda s: HostCommandDriver(
        commands={
            "flush_cache":   "systemctl restart myapp-cache",
            "restart_svc":   "systemctl restart {service}",
            "run_etl":       "/opt/jobs/run.sh {job}",
        },
        transport="ssh", host="app01.internal", user="deploy",
    ))

Then set ``EXECUTION_BACKEND=host`` and add the verbs to that service's contract.
"""

from __future__ import annotations

import logging
import shlex
import subprocess
from typing import Any

from core.execution.drivers.base import ExecutionDriver

logger = logging.getLogger(__name__)


class HostCommandDriver(ExecutionDriver):
    """Run allowlisted commands on a host, or call an HTTP API."""

    def __init__(
        self,
        commands: dict[str, str],
        transport: str = "local",
        host: str | None = None,
        user: str | None = None,
        timeout: int = 30,
        # For restart/start/stop_service and run_batch_job, the command *name*
        # in `commands` used for that verb (templates may reference {service}/{job}).
        service_command: str = "restart_svc",
        start_command: str = "start_svc",
        stop_command: str = "stop_svc",
        batch_command: str = "run_job",
    ) -> None:
        self._commands = dict(commands)
        self._transport = transport
        self._host = host
        self._user = user
        self._timeout = timeout
        self._verb_command = {
            "restart_service": service_command,
            "start_service": start_command,
            "stop_service": stop_command,
            "run_batch_job": batch_command,
        }

    # -- ExecutionDriver interface -----------------------------------------
    def execute(self, action: str, target: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if action == "http_request":
            return self._http(parameters)
        if action == "run_command":
            # `command` names an entry in the allowlist; extra params fill the template.
            name = parameters.get("command")
            if not name:
                return {"success": False, "error": "run_command requires a 'command' parameter naming an allowlisted command"}
            return self._run_named(name, {"target": target, **parameters})
        if action in self._verb_command:
            name = self._verb_command[action]
            return self._run_named(name, {"target": target, "service": target, **parameters})
        return {"success": False, "error": f"Unsupported action for HostCommandDriver: {action}"}

    def get_service_status(self, service: str) -> dict[str, Any]:
        # Optional: point at a status command in the allowlist named "status".
        if "status" in self._commands:
            return self._run_named("status", {"target": service, "service": service})
        return {"service": service, "status": "unknown", "note": "no 'status' command configured"}

    def get_metrics(self, service: str) -> dict[str, Any]:
        if "metrics" in self._commands:
            return self._run_named("metrics", {"target": service, "service": service})
        return {"service": service, "metrics": {}, "note": "no 'metrics' command configured"}

    # -- command transport --------------------------------------------------
    def _run_named(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        template = self._commands.get(name)
        if template is None:
            return {"success": False, "error": f"Command '{name}' is not in the allowlist"}
        safe = {k: shlex.quote(str(v)) for k, v in params.items()}
        try:
            command = template.format(**safe)
        except KeyError as exc:
            return {"success": False, "error": f"Command template needs missing parameter: {exc}"}
        logger.info("HostCommandDriver dispatching (%s): %s", self._transport, command)
        if self._transport == "local":
            return self._local(command)
        if self._transport == "ssh":
            return self._ssh(command)
        if self._transport == "winrm":
            return self._winrm(command)
        return {"success": False, "error": f"Unknown transport: {self._transport}"}

    def _local(self, command: str) -> dict[str, Any]:
        try:
            proc = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=self._timeout,
            )
            return {
                "success": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-2000:],
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Command timed out after {self._timeout}s"}
        except Exception as exc:  # pragma: no cover - defensive
            return {"success": False, "error": str(exc)}

    def _ssh(self, command: str) -> dict[str, Any]:  # pragma: no cover - needs a host
        try:
            import paramiko  # lazy: only needed for the ssh transport
        except ImportError:
            return {"success": False, "error": "ssh transport requires 'paramiko' (pip install paramiko)"}
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(self._host, username=self._user, timeout=self._timeout)
            _stdin, stdout, stderr = client.exec_command(command, timeout=self._timeout)
            code = stdout.channel.recv_exit_status()
            return {
                "success": code == 0,
                "returncode": code,
                "stdout": stdout.read().decode(errors="replace")[-4000:],
                "stderr": stderr.read().decode(errors="replace")[-2000:],
            }
        finally:
            client.close()

    def _winrm(self, command: str) -> dict[str, Any]:  # pragma: no cover - needs a host
        try:
            import winrm  # lazy: only needed for the winrm transport (pywinrm)
        except ImportError:
            return {"success": False, "error": "winrm transport requires 'pywinrm' (pip install pywinrm)"}
        session = winrm.Session(self._host, auth=(self._user, ""))
        r = session.run_ps(command)
        return {
            "success": r.status_code == 0,
            "returncode": r.status_code,
            "stdout": r.std_out.decode(errors="replace")[-4000:],
            "stderr": r.std_err.decode(errors="replace")[-2000:],
        }

    # -- http transport (cloud / SaaS APIs, webhooks) -----------------------
    def _http(self, parameters: dict[str, Any]) -> dict[str, Any]:
        import json as _json
        import urllib.request

        url = parameters.get("url")
        if not url:
            return {"success": False, "error": "http_request requires a 'url' parameter"}
        method = str(parameters.get("method", "POST")).upper()
        headers = dict(parameters.get("headers", {}))
        body = parameters.get("body")
        data = None
        if body is not None:
            data = body.encode() if isinstance(body, str) else _json.dumps(body).encode()
            headers.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                text = resp.read().decode(errors="replace")
                return {"success": 200 <= resp.status < 300, "status": resp.status, "body": text[:4000]}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
