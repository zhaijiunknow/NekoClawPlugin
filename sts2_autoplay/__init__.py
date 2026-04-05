from __future__ import annotations

from typing import Any, Dict, Optional

from plugin.sdk.plugin import NekoPluginBase, neko_plugin, plugin_entry, lifecycle, Ok, Err, SdkError

from .service import STS2AutoplayService


@neko_plugin
class STS2AutoplayPlugin(NekoPluginBase):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.file_logger = self.enable_file_logging(log_level="INFO")
        self.logger = self.file_logger
        self._cfg: Dict[str, Any] = {}
        self._service = STS2AutoplayService(self.logger, self.report_status)

    @lifecycle(id="startup")
    async def startup(self, **_):
        cfg = await self.config.dump(timeout=5.0)
        cfg = cfg if isinstance(cfg, dict) else {}
        self._cfg = cfg.get("sts2", {}) if isinstance(cfg.get("sts2"), dict) else {}
        await self._service.startup(self._cfg)
        return Ok({"status": "ready", "result": await self._service.get_status()})

    @lifecycle(id="shutdown")
    async def shutdown(self, **_):
        await self._service.shutdown()
        return Ok({"status": "shutdown"})

    def _ok(self, payload: Dict[str, Any]) -> Ok:
        summary = payload.get("message") if isinstance(payload.get("message"), str) else payload.get("status", "ok")
        return Ok({"summary": str(summary), "result": payload})

    def _err(self, exc: Exception) -> Err:
        return Err(SdkError(str(exc)))

    @plugin_entry(id="sts2_health_check", name="检查 STS2 服务", description="检查本地 STS2-Agent 服务健康状态。", llm_result_fields=["summary"], input_schema={"type": "object", "properties": {}})
    async def sts2_health_check(self, **_):
        try:
            return self._ok(await self._service.health_check())
        except Exception as e:
            return self._err(e)

    @plugin_entry(id="sts2_refresh_state", name="刷新 STS2 状态", description="强制刷新一次当前游戏状态。", llm_result_fields=["summary"], input_schema={"type": "object", "properties": {}})
    async def sts2_refresh_state(self, **_):
        try:
            return self._ok(await self._service.refresh_state())
        except Exception as e:
            return self._err(e)

    @plugin_entry(id="sts2_get_status", name="获取 STS2 状态", description="获取连接状态、自动游玩状态和最近错误。", llm_result_fields=["summary"], input_schema={"type": "object", "properties": {}})
    async def sts2_get_status(self, **_):
        try:
            payload = await self._service.get_status()
            payload["message"] = f"{payload['server']['state']} | autoplay={payload['autoplay']['state']}"
            return self._ok(payload)
        except Exception as e:
            return self._err(e)

    @plugin_entry(id="sts2_get_snapshot", name="获取 STS2 快照", description="获取最近缓存的游戏快照和合法动作。", llm_result_fields=["summary"], input_schema={"type": "object", "properties": {}})
    async def sts2_get_snapshot(self, **_):
        try:
            payload = await self._service.get_snapshot()
            return self._ok(payload)
        except Exception as e:
            return self._err(e)

    @plugin_entry(id="sts2_step_once", name="执行一步", description="根据当前策略执行一步合法动作。", llm_result_fields=["summary"], input_schema={"type": "object", "properties": {}})
    async def sts2_step_once(self, **_):
        try:
            return self._ok(await self._service.step_once())
        except Exception as e:
            return self._err(e)

    @plugin_entry(id="sts2_start_autoplay", name="开始自动游玩", description="启动后台自动游玩循环。", llm_result_fields=["summary"], input_schema={"type": "object", "properties": {}})
    async def sts2_start_autoplay(self, **_):
        try:
            return self._ok(await self._service.start_autoplay())
        except Exception as e:
            return self._err(e)

    @plugin_entry(id="sts2_pause_autoplay", name="暂停自动游玩", description="暂停后台自动游玩循环。", llm_result_fields=["summary"], input_schema={"type": "object", "properties": {}})
    async def sts2_pause_autoplay(self, **_):
        try:
            return self._ok(await self._service.pause_autoplay())
        except Exception as e:
            return self._err(e)

    @plugin_entry(id="sts2_resume_autoplay", name="恢复自动游玩", description="恢复已暂停的自动游玩循环。", llm_result_fields=["summary"], input_schema={"type": "object", "properties": {}})
    async def sts2_resume_autoplay(self, **_):
        try:
            return self._ok(await self._service.resume_autoplay())
        except Exception as e:
            return self._err(e)

    @plugin_entry(id="sts2_stop_autoplay", name="停止自动游玩", description="停止后台自动游玩循环。", llm_result_fields=["summary"], input_schema={"type": "object", "properties": {}})
    async def sts2_stop_autoplay(self, **_):
        try:
            return self._ok(await self._service.stop_autoplay())
        except Exception as e:
            return self._err(e)

    @plugin_entry(id="sts2_get_history", name="获取历史", description="获取最近动作和状态历史。", llm_result_fields=["summary"], input_schema={"type": "object", "properties": {"limit": {"type": "integer", "default": 20}}})
    async def sts2_get_history(self, limit: int = 20, **_):
        try:
            return self._ok(await self._service.get_history(limit=limit))
        except Exception as e:
            return self._err(e)

    @plugin_entry(id="sts2_set_strategy", name="设置策略", description="设置自动游玩策略。", llm_result_fields=["summary"], input_schema={"type": "object", "properties": {"strategy": {"type": "string", "default": "heuristic"}}, "required": ["strategy"]})
    async def sts2_set_strategy(self, strategy: str, **_):
        try:
            return self._ok(await self._service.set_strategy(strategy))
        except Exception as e:
            return self._err(e)

    @plugin_entry(id="sts2_set_speed", name="设置速度", description="设置动作后等待时间和活跃轮询间隔。", llm_result_fields=["summary"], input_schema={"type": "object", "properties": {"post_action_delay_seconds": {"type": "number"}, "poll_interval_active_seconds": {"type": "number"}}})
    async def sts2_set_speed(self, post_action_delay_seconds: Optional[float] = None, poll_interval_active_seconds: Optional[float] = None, **_):
        try:
            return self._ok(await self._service.set_speed(post_action_delay_seconds=post_action_delay_seconds, poll_interval_active_seconds=poll_interval_active_seconds))
        except Exception as e:
            return self._err(e)
