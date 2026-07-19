"""Summary agent for creating post-incident reports.

The SummaryAgent takes the audit trail of a completed incident execution
and generates a human-readable summary report.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from core.models import BaseIncident as Incident
from core.models import AuditEvent

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert post-incident reporter. \
Your job is to read the audit trail of an autonomous incident remediation \
and write a concise, professional executive summary. \
Include what was detected, what actions were planned and executed, \
and whether human approval was required.
"""

class SummaryAgent:
    def __init__(self, temperature: float = 0.0) -> None:
        from core.llm.factory import get_chat_model

        # Summary role maps to Gemini by default (cheap; degrades gracefully on quota).
        # Fail fast on rate limits so a quota 429 doesn't slow finalize — the summary
        # is best-effort and finalize catches any error.
        self.llm = get_chat_model("summary", temperature=temperature, max_retries=0)
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def summarize(self, incident: Incident, audit_trail: list[dict[str, Any]]) -> str:
        self._logger.info("Generating summary for incident %s", incident.incident_id)
        
        trail_text = "\n".join([str(evt) for evt in audit_trail])
        
        user_content = (
            f"Incident: {incident.incident_id}\n"
            f"Service: {incident.service}\n"
            f"Severity: {incident.severity.value}\n\n"
            f"Audit Trail:\n{trail_text}"
        )
        
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]
        
        response = await self.llm.ainvoke(messages)
        return response.content
