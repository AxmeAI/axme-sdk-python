"""Agent Mesh module - heartbeat, health monitoring, metrics reporting."""
from __future__ import annotations

import threading
import time
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .client import AxmeClient


class MeshClient:
    """Mesh operations for an AxmeClient instance."""

    def __init__(self, client: AxmeClient) -> None:
        self._client = client
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_stop = threading.Event()
        self._metrics_buffer: dict[str, Any] = {}

    # ── Heartbeat ────────────────────────────────────────────────────

    def heartbeat(
        self,
        *,
        metrics: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a single heartbeat to the mesh. Optionally include metrics."""
        body: dict[str, Any] = {}
        if metrics:
            body["metrics"] = metrics
        return self._client._request_json(
            "POST",
            "/v1/mesh/heartbeat",
            json_body=body if body else None,
            retryable=True,
            trace_id=trace_id,
        )

    def start_heartbeat(
        self,
        *,
        interval_seconds: float = 30.0,
        include_metrics: bool = True,
    ) -> None:
        """Start a background thread that sends heartbeats at regular intervals.

        Args:
            interval_seconds: Seconds between heartbeats (default 30).
            include_metrics: Whether to include buffered metrics with each heartbeat.
        """
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            return  # Already running

        self._heartbeat_stop.clear()

        def _loop() -> None:
            while not self._heartbeat_stop.wait(timeout=interval_seconds):
                try:
                    metrics = self._flush_metrics() if include_metrics else None
                    self.heartbeat(metrics=metrics)
                except Exception:
                    pass  # Heartbeat failures are non-fatal

        self._heartbeat_thread = threading.Thread(
            target=_loop, daemon=True, name="axme-mesh-heartbeat",
        )
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        """Stop the background heartbeat thread."""
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=5.0)
            self._heartbeat_thread = None

    # ── Metrics ──────────────────────────────────────────────────────

    def report_metric(
        self,
        *,
        success: bool = True,
        latency_ms: float | None = None,
        cost_usd: float | None = None,
    ) -> None:
        """Buffer a metric observation. Flushed with next heartbeat."""
        buf = self._metrics_buffer
        buf["intents_total"] = buf.get("intents_total", 0) + 1
        if success:
            buf["intents_succeeded"] = buf.get("intents_succeeded", 0) + 1
        else:
            buf["intents_failed"] = buf.get("intents_failed", 0) + 1
        if latency_ms is not None:
            # Running average
            count = buf["intents_total"]
            prev_avg = buf.get("avg_latency_ms", 0.0)
            buf["avg_latency_ms"] = prev_avg + (latency_ms - prev_avg) / count
        if cost_usd is not None:
            buf["cost_usd"] = buf.get("cost_usd", 0.0) + cost_usd

    def _flush_metrics(self) -> dict[str, Any] | None:
        if not self._metrics_buffer:
            return None
        metrics = self._metrics_buffer.copy()
        self._metrics_buffer.clear()
        return metrics

    # ── Agent management ─────────────────────────────────────────────

    def list_agents(
        self,
        *,
        limit: int = 100,
        health: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """List all agents in workspace with health status."""
        params: dict[str, str] = {"limit": str(limit)}
        if health:
            params["health"] = health
        return self._client._request_json(
            "GET",
            "/v1/mesh/agents",
            params=params,
            retryable=True,
            trace_id=trace_id,
        )

    def get_agent(
        self,
        address_id: str,
        *,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Get single agent detail with metrics and events."""
        return self._client._request_json(
            "GET",
            f"/v1/mesh/agents/{address_id}",
            retryable=True,
            trace_id=trace_id,
        )

    def kill(
        self,
        address_id: str,
        *,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Kill an agent - block all intents to and from it."""
        return self._client._request_json(
            "POST",
            f"/v1/mesh/agents/{address_id}/kill",
            retryable=False,
            trace_id=trace_id,
        )

    def resume(
        self,
        address_id: str,
        *,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Resume a killed agent."""
        return self._client._request_json(
            "POST",
            f"/v1/mesh/agents/{address_id}/resume",
            retryable=False,
            trace_id=trace_id,
        )

    def list_events(
        self,
        *,
        limit: int = 50,
        event_type: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """List recent mesh events (kills, resumes, health changes)."""
        params: dict[str, str] = {"limit": str(limit)}
        if event_type:
            params["event_type"] = event_type
        return self._client._request_json(
            "GET",
            "/v1/mesh/events",
            params=params,
            retryable=True,
            trace_id=trace_id,
        )
