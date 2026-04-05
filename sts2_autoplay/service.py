from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, Optional

from .client import STS2ApiClient, STS2ClientError
from .models import normalize_snapshot


class STS2AutoplayService:
    def __init__(self, logger, status_reporter: Callable[[dict[str, Any]], None]) -> None:
        self.logger = logger
        self._report_status = status_reporter
        self._client: Optional[STS2ApiClient] = None
        self._cfg: Dict[str, Any] = {}
        self._snapshot: Dict[str, Any] = {}
        self._history: Deque[Dict[str, Any]] = deque(maxlen=100)
        self._poll_task: Optional[asyncio.Task] = None
        self._autoplay_task: Optional[asyncio.Task] = None
        self._shutdown = False
        self._paused = False
        self._server_state = "disconnected"
        self._autoplay_state = "disabled"
        self._last_error = ""
        self._last_action = ""
        self._last_poll_at = 0.0
        self._last_action_at = 0.0
        self._consecutive_errors = 0

    async def startup(self, cfg: Dict[str, Any]) -> None:
        self._cfg = dict(cfg)
        self._shutdown = False
        self._paused = False
        self._autoplay_state = "idle"
        self._client = STS2ApiClient(
            base_url=str(self._cfg.get("base_url") or "http://127.0.0.1:8080"),
            connect_timeout=float(self._cfg.get("connect_timeout_seconds", 5) or 5),
            request_timeout=float(self._cfg.get("request_timeout_seconds", 15) or 15),
        )
        try:
            await self.health_check()
        except Exception:
            pass
        self._poll_task = asyncio.create_task(self._poll_loop())
        if bool(self._cfg.get("autoplay_on_start", False)):
            await self.start_autoplay()

    async def shutdown(self) -> None:
        self._shutdown = True
        await self.stop_autoplay()
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except Exception:
                pass
            self._poll_task = None
        if self._client is not None:
            await self._client.close()
            self._client = None
        self._server_state = "disconnected"
        self._emit_status()

    async def health_check(self) -> Dict[str, Any]:
        client = self._require_client()
        data = await client.health()
        self._server_state = "connected"
        self._last_error = ""
        self._emit_status()
        return {"status": "connected", "message": f"STS2-Agent 已连接: {client.base_url}", "health": data}

    async def refresh_state(self) -> Dict[str, Any]:
        client = self._require_client()
        state_payload = await client.get_state()
        actions_payload = await client.get_available_actions()
        self._snapshot = normalize_snapshot(state_payload, actions_payload)
        self._server_state = "connected"
        self._last_error = ""
        self._last_poll_at = time.time()
        self._history.appendleft({"type": "snapshot", "time": self._last_poll_at, "screen": self._snapshot.get("screen"), "available_actions": self._snapshot.get("available_action_count", 0)})
        self._emit_status()
        return {"status": "ok", "message": f"已刷新状态，screen={self._snapshot.get('screen')}", "snapshot": self._snapshot}

    async def get_status(self) -> Dict[str, Any]:
        return {
            "server": {"state": self._server_state, "base_url": self._cfg.get("base_url", "http://127.0.0.1:8080")},
            "autoplay": {"state": self._autoplay_state, "strategy": self._cfg.get("strategy", "heuristic"), "paused": self._paused},
            "run": {
                "screen": self._snapshot.get("screen", "unknown"),
                "floor": self._snapshot.get("floor", 0),
                "act": self._snapshot.get("act", 0),
                "in_combat": self._snapshot.get("in_combat", False),
                "available_action_count": self._snapshot.get("available_action_count", 0),
            },
            "decision": {"last_action": self._last_action, "last_error": self._last_error},
            "timestamps": {"last_poll_at": self._last_poll_at, "last_action_at": self._last_action_at},
        }

    async def get_snapshot(self) -> Dict[str, Any]:
        if not self._snapshot:
            await self.refresh_state()
        return {"status": "ok", "message": "当前快照", "snapshot": self._snapshot}

    async def step_once(self) -> Dict[str, Any]:
        if not self._snapshot:
            await self.refresh_state()
        actions = self._snapshot.get("available_actions") if isinstance(self._snapshot.get("available_actions"), list) else []
        if not actions:
            return {"status": "idle", "message": "当前没有可执行动作", "snapshot": self._snapshot}
        action = self._select_action(actions)
        result = await self._execute_action(action)
        await asyncio.sleep(float(self._cfg.get("post_action_delay_seconds", 0.5) or 0.5))
        await self.refresh_state()
        return result

    async def start_autoplay(self) -> Dict[str, Any]:
        if self._autoplay_task and not self._autoplay_task.done():
            return {"status": "running", "message": "自动游玩已在运行"}
        self._paused = False
        self._autoplay_state = "running"
        self._autoplay_task = asyncio.create_task(self._autoplay_loop())
        self._emit_status()
        return {"status": "running", "message": "自动游玩已启动"}

    async def pause_autoplay(self) -> Dict[str, Any]:
        self._paused = True
        if self._autoplay_state == "running":
            self._autoplay_state = "paused"
        self._emit_status()
        return {"status": "paused", "message": "自动游玩已暂停"}

    async def resume_autoplay(self) -> Dict[str, Any]:
        if self._autoplay_task is None or self._autoplay_task.done():
            return await self.start_autoplay()
        self._paused = False
        self._autoplay_state = "running"
        self._emit_status()
        return {"status": "running", "message": "自动游玩已恢复"}

    async def stop_autoplay(self) -> Dict[str, Any]:
        self._paused = False
        if self._autoplay_task is not None:
            self._autoplay_task.cancel()
            try:
                await self._autoplay_task
            except Exception:
                pass
            self._autoplay_task = None
        self._autoplay_state = "idle"
        self._emit_status()
        return {"status": "idle", "message": "自动游玩已停止"}

    async def get_history(self, limit: int = 20) -> Dict[str, Any]:
        limit = max(1, min(100, int(limit or 20)))
        items = list(self._history)[:limit]
        return {"status": "ok", "message": f"最近 {len(items)} 条历史", "history": items}

    async def set_strategy(self, strategy: str) -> Dict[str, Any]:
        strategy = (strategy or "heuristic").strip().lower()
        if strategy not in {"heuristic"}:
            raise RuntimeError(f"暂不支持策略: {strategy}")
        self._cfg["strategy"] = strategy
        self._emit_status()
        return {"status": "ok", "message": f"策略已切换为 {strategy}", "strategy": strategy}

    async def set_speed(self, *, post_action_delay_seconds: Optional[float] = None, poll_interval_active_seconds: Optional[float] = None) -> Dict[str, Any]:
        if post_action_delay_seconds is not None:
            self._cfg["post_action_delay_seconds"] = max(0.0, float(post_action_delay_seconds))
        if poll_interval_active_seconds is not None:
            self._cfg["poll_interval_active_seconds"] = max(0.1, float(poll_interval_active_seconds))
        return {"status": "ok", "message": "速度设置已更新", "post_action_delay_seconds": self._cfg.get("post_action_delay_seconds"), "poll_interval_active_seconds": self._cfg.get("poll_interval_active_seconds")}

    async def _poll_loop(self) -> None:
        while not self._shutdown:
            try:
                await self.refresh_state()
                self._consecutive_errors = 0
            except Exception as exc:
                self._consecutive_errors += 1
                self._server_state = "degraded" if self._consecutive_errors < int(self._cfg.get("max_consecutive_errors", 3) or 3) else "disconnected"
                self._last_error = str(exc)
                self._emit_status()
            interval = float(self._cfg.get("poll_interval_active_seconds", 1) if self._autoplay_state == "running" else self._cfg.get("poll_interval_idle_seconds", 3))
            await asyncio.sleep(max(0.1, interval))

    async def _autoplay_loop(self) -> None:
        try:
            while not self._shutdown:
                if self._paused:
                    await asyncio.sleep(0.2)
                    continue
                result = await self.step_once()
                if result.get("status") == "idle":
                    await asyncio.sleep(max(0.2, float(self._cfg.get("poll_interval_active_seconds", 1) or 1)))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._autoplay_state = "error"
            self._last_error = str(exc)
            self._emit_status()

    def _select_action(self, actions: list[dict[str, Any]]) -> dict[str, Any]:
        for action in actions:
            action_type = str(action.get("type") or "")
            if action_type and action_type not in {"wait", "noop"}:
                return action
        return actions[0]

    async def _execute_action(self, action: dict[str, Any]) -> Dict[str, Any]:
        client = self._require_client()
        raw = action.get("raw") if isinstance(action.get("raw"), dict) else {}
        action_type = str(action.get("type") or raw.get("type") or "")
        kwargs = {k: v for k, v in raw.items() if k != "type"}
        result = await client.execute_action(action_type, **kwargs)
        self._last_action = action_type
        self._last_action_at = time.time()
        self._history.appendleft({"type": "action", "time": self._last_action_at, "action": action_type, "result": result})
        self._emit_status()
        return {"status": "ok", "message": f"已执行动作: {action_type}", "action": action_type, "result": result}

    def _require_client(self) -> STS2ApiClient:
        if self._client is None:
            raise RuntimeError("STS2 客户端未初始化")
        return self._client

    def _emit_status(self) -> None:
        try:
            self._report_status({
                "server": {"state": self._server_state, "base_url": self._cfg.get("base_url", "http://127.0.0.1:8080")},
                "autoplay": {"state": self._autoplay_state, "strategy": self._cfg.get("strategy", "heuristic")},
                "run": {"screen": self._snapshot.get("screen", "unknown"), "floor": self._snapshot.get("floor", 0), "available_action_count": self._snapshot.get("available_action_count", 0)},
                "decision": {"last_action": self._last_action, "last_error": self._last_error},
            })
        except Exception:
            pass
