from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote

import httpx

from plugin.sdk.plugin import NekoPluginBase, lifecycle, neko_plugin, plugin_entry, Ok, Err, SdkError


@neko_plugin
class DGLabHubPlugin(NekoPluginBase):

    def __init__(self, ctx):
        super().__init__(ctx)
        self.file_logger = self.enable_file_logging(log_level="INFO")
        self.logger = self.file_logger
        self._base_url = "http://127.0.0.1:8920"
        self._default_client_id = ""
        self._timeout = 10.0
        self._allow_broadcast_all = False
        self._auto_start_hub = False
        self._hub_dir = "coyote-game-hub"
        self._startup_timeout = 20.0
        self._show_hub_window = False
        self._hub_process: Optional[asyncio.subprocess.Process] = None
        self._hub_stdout_task: Optional[asyncio.Task] = None
        self._hub_stderr_task: Optional[asyncio.Task] = None
        self._managed_hub_started = False

    @lifecycle(id="startup")
    async def startup(self, **_):
        cfg = await self.config.dump(timeout=5.0)
        cfg = cfg if isinstance(cfg, dict) else {}
        hub_cfg = cfg.get("dg_lab_hub", {}) if isinstance(cfg.get("dg_lab_hub"), dict) else {}

        self._base_url = str(hub_cfg.get("base_url", "http://127.0.0.1:8920")).strip().rstrip("/")
        self._default_client_id = str(hub_cfg.get("client_id", "")).strip()
        self._timeout = float(hub_cfg.get("timeout_seconds", 10))
        self._allow_broadcast_all = bool(hub_cfg.get("allow_broadcast_all", False))
        self._auto_start_hub = bool(hub_cfg.get("auto_start_hub", False))
        self._hub_dir = str(hub_cfg.get("hub_dir", "coyote-game-hub")).strip() or "coyote-game-hub"
        self._startup_timeout = float(hub_cfg.get("startup_timeout_seconds", 20))
        self._show_hub_window = bool(hub_cfg.get("show_hub_window", False))

        if not self._base_url:
            return Err(SdkError("DG-Lab Hub base_url 未配置"))

        hub_online = await self._is_hub_online()
        if hub_online:
            self.logger.info("DGLabHub detected existing service at {}", self._base_url)
            if not self._default_client_id:
                try:
                    resolved = await self._get_effective_client_id(None)
                    self.logger.info(
                        "DGLabHub auto-preloaded client_id={} source={}",
                        resolved["client_id"],
                        resolved["source"],
                    )
                except SdkError as exc:
                    self.logger.warning("DGLabHub failed to auto-acquire client_id during startup: {}", exc)
        else:
            self.logger.info("DGLabHub startup completed without auto-start; use start_hub entry to launch {}", self._hub_dir)

        self.logger.info(
            "DGLabHub started: base_url={}, default_client_id={}, timeout={}s, allow_broadcast_all={}, auto_start_hub={}, hub_dir={}, hub_online={}",
            self._base_url,
            self._default_client_id or "<empty>",
            self._timeout,
            self._allow_broadcast_all,
            self._auto_start_hub,
            self._hub_dir,
            hub_online,
        )
        return Ok({
            "status": "running",
            "base_url": self._base_url,
            "default_client_id": self._default_client_id,
            "allow_broadcast_all": self._allow_broadcast_all,
            "auto_start_hub": self._auto_start_hub,
            "managed_hub_started": self._managed_hub_started,
            "hub_online": hub_online,
        })

    @lifecycle(id="shutdown")
    async def shutdown(self, **_):
        await self._stop_hub_managed()
        self.logger.info("DGLabHub shutdown")
        return Ok({"status": "shutdown"})

    async def _fetch_client_connect_info(self) -> Dict[str, Any]:
        url = self._build_url("/api/client/connect")
        try:
            async with httpx.AsyncClient(timeout=self._timeout, proxy=None, trust_env=False) as client:
                resp = await client.get(url)
        except httpx.TimeoutException as exc:
            raise SdkError("请求 DG-Lab Hub 获取 client_id 超时") from exc
        except httpx.HTTPError as exc:
            raise SdkError(f"DG-Lab Hub 不可达: {exc}") from exc
        except Exception as exc:
            raise SdkError(f"请求 DG-Lab Hub 获取 client_id 失败: {exc}") from exc

        if resp.status_code != 200:
            body_text = (resp.text or "").strip()
            body_text = body_text[:300] if body_text else "<empty>"
            raise SdkError(f"Hub HTTP {resp.status_code}: {body_text}")

        try:
            payload = resp.json()
        except Exception as exc:
            raise SdkError(f"响应解析失败: {exc}") from exc

        normalized = self._normalize_payload(payload)
        client_id = str(normalized.get("clientId", "")).strip()
        if not client_id:
            raise SdkError("Hub 未返回有效的 clientId")
        normalized["clientId"] = client_id
        return normalized

    async def _resolve_client_id(self, client_id: Optional[str]) -> Tuple[str, str]:
        requested = str(client_id or "").strip()
        if requested:
            if requested == "all" and not self._allow_broadcast_all:
                raise SdkError("当前插件未允许广播到 all，请在配置中启用 allow_broadcast_all")
            return requested, "input"

        configured = self._default_client_id.strip()
        if configured:
            if configured == "all" and not self._allow_broadcast_all:
                raise SdkError("当前插件未允许广播到 all，请在配置中启用 allow_broadcast_all")
            return configured, "config"

        acquired = await self._fetch_client_connect_info()
        acquired_client_id = str(acquired["clientId"]).strip()
        if acquired_client_id == "all":
            raise SdkError("Hub 返回了无效的 clientId: all")
        self._default_client_id = acquired_client_id
        self.logger.info("DGLabHub auto-acquired client_id={}", acquired_client_id)
        return acquired_client_id, "auto"

    async def _get_effective_client_id(self, client_id: Optional[str]) -> Dict[str, str]:
        resolved_client_id, source = await self._resolve_client_id(client_id)
        return {
            "client_id": resolved_client_id,
            "source": source,
        }

    def _build_url(self, path: str, client_id: Optional[str] = None) -> str:
        if client_id is None:
            return f"{self._base_url}{path}"
        encoded_client_id = quote(client_id, safe="")
        return f"{self._base_url}{path.format(clientId=encoded_client_id)}"

    def _normalize_payload(self, payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise SdkError("Hub 响应不是 JSON 对象")
        if payload.get("status") == 0:
            code = str(payload.get("code", "ERR::UNKNOWN"))
            message = str(payload.get("message", "Hub 返回失败"))
            raise SdkError(f"{code}: {message}")
        return payload

    def _hub_root(self) -> Path:
        return self.config_dir / self._hub_dir

    def _resolve_hub_command(self) -> tuple[list[str], Path, subprocess.STARTUPINFO | None]:
        hub_root = self._hub_root()
        if not hub_root.exists():
            raise SdkError(f"DG-Lab Hub 目录不存在: {hub_root}")

        startupinfo = None
        if os.name == "nt" and not self._show_hub_window:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        start_bat = hub_root / "start.bat"
        bundled_server = hub_root / "server" / "index.js"
        dist_server = hub_root / "server" / "dist" / "index.js"

        if start_bat.is_file():
            if os.name == "nt":
                return ["cmd", "/c", str(start_bat)], hub_root, startupinfo
            return [str(start_bat)], hub_root, startupinfo

        if bundled_server.is_file():
            return ["node", str(bundled_server)], hub_root, startupinfo

        if dist_server.is_file():
            return ["node", str(dist_server)], hub_root / "server", startupinfo

        raise SdkError(
            "未找到可启动的 DG-Lab Hub 入口，请确认插件目录内已放入构建后的 Hub（start.bat / server/index.js / server/dist/index.js）"
        )

    async def _pipe_stream(self, stream, prefix: str):
        if stream is None:
            return
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    self.logger.info("[Hub] {}{}", prefix, text)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.logger.warning("DGLabHub log pipe error [{}]: {}", prefix or "stdout", exc)

    async def _cancel_hub_log_tasks(self):
        for attr in ("_hub_stdout_task", "_hub_stderr_task"):
            task = getattr(self, attr)
            if task is None:
                continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            setattr(self, attr, None)

    async def _is_hub_online(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=min(self._timeout, 2.0), proxy=None, trust_env=False) as client:
                resp = await client.get(self._build_url("/api/v2/game"))
                if resp.status_code != 200:
                    return False
                payload = resp.json()
                return isinstance(payload, dict) and payload.get("status") == 1
        except Exception:
            return False

    async def _wait_for_hub_ready(self):
        deadline = asyncio.get_running_loop().time() + max(self._startup_timeout, 1.0)
        while asyncio.get_running_loop().time() < deadline:
            if await self._is_hub_online():
                return
            if self._hub_process is not None and self._hub_process.returncode is not None:
                raise SdkError(f"DG-Lab Hub 进程已退出，返回码: {self._hub_process.returncode}")
            await asyncio.sleep(0.5)
        raise SdkError(f"等待 DG-Lab Hub 启动超时（>{self._startup_timeout} 秒）")

    async def _start_hub_managed(self, *, show_window: Optional[bool] = None) -> Dict[str, Any]:
        if self._hub_process is not None and self._hub_process.returncode is None:
            self.logger.info("DGLabHub managed process already running, pid={}", self._hub_process.pid)
            await self._wait_for_hub_ready()
            self._managed_hub_started = True
            return {
                "status": "already_running",
                "base_url": self._base_url,
                "pid": self._hub_process.pid,
                "managed": True,
            }

        if await self._is_hub_online():
            self.logger.info("DGLabHub start requested but existing service is already online at {}", self._base_url)
            return {
                "status": "already_online",
                "base_url": self._base_url,
                "managed": False,
            }

        original_show_hub_window = self._show_hub_window
        if show_window is not None:
            self._show_hub_window = bool(show_window)

        try:
            cmd, cwd, startupinfo = self._resolve_hub_command()
            self.logger.info("Starting DG-Lab Hub from {} with command: {}", cwd, cmd)
            try:
                kwargs = {
                    "cwd": str(cwd),
                    "stdout": asyncio.subprocess.PIPE,
                    "stderr": asyncio.subprocess.PIPE,
                }
                if startupinfo is not None:
                    kwargs["startupinfo"] = startupinfo
                self._hub_process = await asyncio.create_subprocess_exec(*cmd, **kwargs)
            except FileNotFoundError as exc:
                raise SdkError(f"启动 DG-Lab Hub 失败，缺少运行环境或命令不可用: {exc}") from exc
            except Exception as exc:
                raise SdkError(f"启动 DG-Lab Hub 失败: {exc}") from exc

            self._managed_hub_started = True
            self._hub_stdout_task = asyncio.create_task(self._pipe_stream(self._hub_process.stdout, ""))
            self._hub_stderr_task = asyncio.create_task(self._pipe_stream(self._hub_process.stderr, "[ERR] "))

            try:
                await self._wait_for_hub_ready()
                self.logger.info("DG-Lab Hub is ready, pid={}", self._hub_process.pid)
                return {
                    "status": "started",
                    "base_url": self._base_url,
                    "pid": self._hub_process.pid,
                    "managed": True,
                }
            except Exception:
                await self._stop_hub_managed()
                raise
        finally:
            self._show_hub_window = original_show_hub_window

    async def _stop_hub_managed(self) -> Dict[str, Any]:
        await self._cancel_hub_log_tasks()

        if not self._managed_hub_started:
            self._hub_process = None
            return {"status": "not_managed", "managed": False}

        proc = self._hub_process
        self._hub_process = None
        self._managed_hub_started = False

        if proc is None or proc.returncode is not None:
            return {"status": "already_stopped", "managed": True}

        self.logger.info("Stopping DG-Lab Hub process, pid={}", proc.pid)
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
            return {"status": "stopped", "managed": True, "pid": proc.pid}
        except asyncio.TimeoutError:
            self.logger.warning("DG-Lab Hub did not exit after terminate, killing pid={}", proc.pid)
            proc.kill()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
                return {"status": "killed", "managed": True, "pid": proc.pid}
            except asyncio.TimeoutError:
                self.logger.warning("DG-Lab Hub kill wait timed out, pid={}", proc.pid)
                return {"status": "kill_timeout", "managed": True, "pid": proc.pid}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        client_id: Optional[str] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ):
        try:
            resolved = await self._get_effective_client_id(client_id)
            resolved_client_id = resolved["client_id"]
            url = self._build_url(path, resolved_client_id)
        except SdkError as exc:
            return Err(exc)

        try:
            async with httpx.AsyncClient(timeout=self._timeout, proxy=None, trust_env=False) as client:
                if method.upper() == "GET":
                    resp = await client.get(url)
                elif method.upper() == "POST":
                    resp = await client.post(url, json=json_data)
                else:
                    return Err(SdkError(f"不支持的 HTTP 方法: {method}"))
        except httpx.TimeoutException:
            self.logger.warning("DGLabHub request timeout: {} {}", method, url)
            return Err(SdkError("请求 DG-Lab Hub 超时"))
        except httpx.HTTPError as exc:
            self.logger.warning("DGLabHub request failed: {} {} -> {}", method, url, exc)
            return Err(SdkError(f"DG-Lab Hub 不可达: {exc}"))
        except Exception as exc:
            self.logger.exception("DGLabHub unexpected request error: {} {}", method, url)
            return Err(SdkError(f"请求 DG-Lab Hub 失败: {exc}"))

        if resp.status_code != 200:
            body_text = (resp.text or "").strip()
            body_text = body_text[:300] if body_text else "<empty>"
            self.logger.warning("DGLabHub HTTP {}: {} -> {}", resp.status_code, url, body_text)
            return Err(SdkError(f"Hub HTTP {resp.status_code}: {body_text}"))

        try:
            payload = resp.json()
        except Exception as exc:
            self.logger.warning("DGLabHub invalid JSON: {} -> {}", url, exc)
            return Err(SdkError(f"响应解析失败: {exc}"))

        try:
            normalized = self._normalize_payload(payload)
        except SdkError as exc:
            self.logger.warning("DGLabHub business error: {} -> {}", url, exc)
            return Err(exc)

        return Ok(normalized)

    @plugin_entry(
        id="start_hub",
        name="启动 DG-Lab Hub",
        description="手动启动插件目录中的 coyote-game-hub 服务；如果 Hub 已在线则直接复用。",
        input_schema={
            "type": "object",
            "properties": {
                "show_window": {
                    "type": "boolean",
                    "description": "可选。是否显示 Hub 窗口；不传时使用插件配置。",
                },
            },
        },
    )
    async def start_hub(self, show_window: Optional[bool] = None, **_):
        try:
            result = await self._start_hub_managed(show_window=show_window)
            return Ok(result)
        except SdkError as exc:
            return Err(exc)

    @plugin_entry(
        id="stop_hub",
        name="停止 DG-Lab Hub",
        description="停止由当前插件启动的 DG-Lab Hub；不会杀掉外部手动启动的 Hub。",
        input_schema={
            "type": "object",
            "properties": {},
        },
    )
    async def stop_hub(self, **_):
        return Ok(await self._stop_hub_managed())

    @plugin_entry(
        id="ensure_client_id",
        name="获取 DG-Lab client_id",
        description="返回当前有效的 DG-Lab Hub clientId；为空时会自动从 Hub 申请一个并缓存到当前插件进程。",
        input_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string", "description": "可选。显式指定 clientId；为空时优先使用配置，否则自动获取。"},
            },
        },
    )
    async def ensure_client_id(self, client_id: Optional[str] = None, **_):
        try:
            resolved = await self._get_effective_client_id(client_id)
            return Ok({
                "status": "ready",
                "base_url": self._base_url,
                "client_id": resolved["client_id"],
                "source": resolved["source"],
            })
        except SdkError as exc:
            return Err(exc)

    @plugin_entry(
        id="get_game_info",
        name="获取 DG-Lab 状态",
        description="查询 DG-Lab-Coyote-Game-Hub 中指定 clientId 的当前状态，包括强度配置、客户端强度和当前波形。",
        input_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string", "description": "可选。Hub 中的目标 clientId；为空时使用插件默认配置。"},
            },
        },
    )
    async def get_game_info(self, client_id: Optional[str] = None, **_):
        return await self._request("GET", "/api/v2/game/{clientId}", client_id=client_id)

    @plugin_entry(
        id="set_strength",
        name="设置 DG-Lab 强度",
        description="设置或调整 DG-Lab 的基础强度和随机强度，对应 Hub 的 /strength 接口。",
        input_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "strength_add": {"type": "number"},
                "strength_sub": {"type": "number"},
                "strength_set": {"type": "number"},
                "random_strength_add": {"type": "number"},
                "random_strength_sub": {"type": "number"},
                "random_strength_set": {"type": "number"},
            },
        },
    )
    async def set_strength(
        self,
        client_id: Optional[str] = None,
        strength_add: Optional[float] = None,
        strength_sub: Optional[float] = None,
        strength_set: Optional[float] = None,
        random_strength_add: Optional[float] = None,
        random_strength_sub: Optional[float] = None,
        random_strength_set: Optional[float] = None,
        **_,
    ):
        body: Dict[str, Any] = {}

        if strength_add is not None or strength_sub is not None or strength_set is not None:
            body["strength"] = {}
            if strength_add is not None:
                body["strength"]["add"] = strength_add
            if strength_sub is not None:
                body["strength"]["sub"] = strength_sub
            if strength_set is not None:
                body["strength"]["set"] = strength_set

        if random_strength_add is not None or random_strength_sub is not None or random_strength_set is not None:
            body["randomStrength"] = {}
            if random_strength_add is not None:
                body["randomStrength"]["add"] = random_strength_add
            if random_strength_sub is not None:
                body["randomStrength"]["sub"] = random_strength_sub
            if random_strength_set is not None:
                body["randomStrength"]["set"] = random_strength_set

        if not body:
            return Err(SdkError("至少需要提供一个强度修改参数"))

        return await self._request("POST", "/api/v2/game/{clientId}/strength", client_id=client_id, json_data=body)

    @plugin_entry(
        id="get_pulse",
        name="获取 DG-Lab 当前波形",
        description="获取指定 clientId 当前生效的 pulseId 或 pulseId 列表。",
        input_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string", "description": "可选。为空时使用插件默认配置。"},
            },
        },
    )
    async def get_pulse(self, client_id: Optional[str] = None, **_):
        return await self._request("GET", "/api/v2/game/{clientId}/pulse", client_id=client_id)

    @plugin_entry(
        id="set_pulse",
        name="设置 DG-Lab 波形",
        description="设置指定 clientId 的波形，可以传单个 pulseId 或 pulseId 列表。",
        input_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "pulse_id": {
                    "description": "单个波形 ID 或波形 ID 列表",
                    "anyOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                },
            },
            "required": ["pulse_id"],
        },
    )
    async def set_pulse(self, pulse_id: Any, client_id: Optional[str] = None, **_):
        if isinstance(pulse_id, str):
            pulse_payload: Any = pulse_id.strip()
            if not pulse_payload:
                return Err(SdkError("pulse_id 不能为空"))
        elif isinstance(pulse_id, list) and pulse_id:
            pulse_payload = [str(item).strip() for item in pulse_id if str(item).strip()]
            if not pulse_payload:
                return Err(SdkError("pulse_id 列表不能为空"))
        else:
            return Err(SdkError("pulse_id 必须是非空字符串或非空字符串数组"))

        return await self._request(
            "POST",
            "/api/v2/game/{clientId}/pulse",
            client_id=client_id,
            json_data={"pulseId": pulse_payload},
        )

    @plugin_entry(
        id="fire",
        name="DG-Lab 一键开火",
        description="通过 Hub 对指定 clientId 触发一键开火，可指定强度、时长、override 和临时波形。",
        input_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "strength": {"type": "number", "description": "开火强度"},
                "time": {"type": "number", "description": "可选，持续时间（毫秒）"},
                "override": {"type": "boolean", "description": "可选，是否覆盖之前的 fire 时间"},
                "pulse_id": {"type": "string", "description": "可选，临时波形 ID"},
            },
            "required": ["strength"],
        },
    )
    async def fire(
        self,
        strength: float,
        client_id: Optional[str] = None,
        time: Optional[float] = None,
        override: Optional[bool] = None,
        pulse_id: Optional[str] = None,
        **_,
    ):
        body: Dict[str, Any] = {"strength": strength}
        if time is not None:
            body["time"] = time
        if override is not None:
            body["override"] = override
        if pulse_id is not None:
            pulse_value = str(pulse_id).strip()
            if not pulse_value:
                return Err(SdkError("pulse_id 不能为空字符串"))
            body["pulseId"] = pulse_value

        return await self._request("POST", "/api/v2/game/{clientId}/action/fire", client_id=client_id, json_data=body)
