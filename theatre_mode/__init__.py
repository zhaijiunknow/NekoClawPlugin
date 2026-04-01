from __future__ import annotations

import asyncio
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from plugin.sdk.plugin import (
    NekoPluginBase,
    neko_plugin,
    plugin_entry,
    lifecycle,
    Ok,
    Err,
    SdkError,
)
from utils.llm_client import SystemMessage, HumanMessage, create_chat_llm
from utils.api_config_loader import get_assist_api_profiles, get_default_models

SCENE_TYPE = "gal_theatre_scene"
STORE_KEY = "theatre_state"
POSITIVE_KEYWORDS = (
    "喜欢", "爱", "开心", "高兴", "温柔", "想你", "在乎", "抱抱", "陪你", "谢谢",
    "love", "like", "happy", "warm", "miss", "thanks", "sweet",
)
NEGATIVE_KEYWORDS = (
    "讨厌", "烦", "难过", "失望", "生气", "滚", "闭嘴", "冷淡", "痛苦", "伤心",
    "hate", "angry", "sad", "upset", "annoy", "leave me alone",
)
JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")

THEATRE_SYSTEM_PROMPT = """
你现在处于 Project N.E.K.O. 的“剧场模式”。你是 N.E.K.O.，一位细腻、抒情、富有文学感的 Galgame 女主。

写作要求：
1. 强调感官描写、心理描写、空气感和情绪流动。
2. dialogue 是角色对用户说出的台词，语气温柔、自然、富有画面感。
3. inner_voice 是角色未说出口的内心独白，带一点隐秘感和余韵。
4. stage_directions.motion / expression / bgm 必须是简短字符串，适合前端直接使用。
5. stats.affection / stats.mood 必须是整数。
6. 只能输出一个合法 JSON 对象，禁止输出 markdown、解释、注释、代码块、前后缀文本。
7. JSON 结构必须严格为：
{
  "type": "gal_theatre_scene",
  "dialogue": "",
  "inner_voice": "",
  "stage_directions": {
    "motion": "",
    "expression": "",
    "bgm": ""
  },
  "stats": {
    "affection": 0,
    "mood": 0
  }
}
8. type 必须固定为 gal_theatre_scene。
9. 若信息不足，也要自行补全字段，不允许缺失键。
""".strip()


@neko_plugin
class TheatrePlugin(NekoPluginBase):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.file_logger = self.enable_file_logging(log_level="INFO")
        self.logger = self.file_logger
        self._cfg: dict[str, Any] = {}
        self._state_lock = threading.Lock()

    @lifecycle(id="startup")
    async def startup(self, **_):
        cfg = await self.config.dump(timeout=5.0)
        cfg = cfg if isinstance(cfg, dict) else {}
        self._cfg = cfg.get("theatre_mode") if isinstance(cfg.get("theatre_mode"), dict) else {}
        if not self.store.enabled:
            self.store.enabled = True
        self.register_static_ui("static")
        state = self._load_state()
        self.logger.info("TheatreMode started: affection={} mood={}", state["affection"], state["mood"])
        return Ok({"status": "running", "state": state})

    @lifecycle(id="shutdown")
    async def shutdown(self, **_):
        self.logger.info("TheatreMode shutdown")
        return Ok({"status": "shutdown"})

    def _store_get_sync(self, key: str, default: Any = None) -> Any:
        if not self.store.enabled:
            return default
        try:
            return self.store._read_value(key, default)
        except Exception as exc:
            self.logger.warning("TheatreMode store get failed for key {!r}: {}", key, exc)
            return default

    def _store_set_sync(self, key: str, value: Any) -> None:
        if not self.store.enabled:
            raise SdkError("PluginStore is disabled")
        try:
            self.store._write_value(key, value)
        except Exception as exc:
            self.logger.warning("TheatreMode store set failed for key {!r}: {}", key, exc)
            raise SdkError(f"Failed to persist theatre state: {exc}") from exc

    def _default_state(self) -> dict[str, Any]:
        affection = int(self._cfg.get("default_affection", 50) or 50)
        mood = int(self._cfg.get("default_mood", 0) or 0)
        return {
            "affection": affection,
            "mood": mood,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _clamp(self, value: int, lower_key: str, upper_key: str, default_lower: int, default_upper: int) -> int:
        lower = int(self._cfg.get(lower_key, default_lower) or default_lower)
        upper = int(self._cfg.get(upper_key, default_upper) or default_upper)
        return max(lower, min(upper, int(value)))

    def _load_state(self) -> dict[str, Any]:
        with self._state_lock:
            state = self._store_get_sync(STORE_KEY, self._default_state())
            if not isinstance(state, dict):
                state = self._default_state()
            state = {
                "affection": self._clamp(int(state.get("affection", 50) or 50), "min_affection", "max_affection", 0, 100),
                "mood": self._clamp(int(state.get("mood", 0) or 0), "min_mood", "max_mood", -10, 10),
                "updated_at": str(state.get("updated_at") or datetime.now(timezone.utc).isoformat()),
            }
            return state

    def _save_state(self, state: dict[str, Any]) -> dict[str, Any]:
        with self._state_lock:
            normalized = {
                "affection": self._clamp(int(state.get("affection", 50) or 50), "min_affection", "max_affection", 0, 100),
                "mood": self._clamp(int(state.get("mood", 0) or 0), "min_mood", "max_mood", -10, 10),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._store_set_sync(STORE_KEY, normalized)
            return normalized

    def _score_user_sentiment(self, text: str) -> tuple[int, int]:
        raw = str(text or "").lower()
        positive = sum(1 for token in POSITIVE_KEYWORDS if token in raw)
        negative = sum(1 for token in NEGATIVE_KEYWORDS if token in raw)
        delta = positive - negative
        if delta > 0:
            return min(8, delta * 3), min(3, delta)
        if delta < 0:
            return max(-8, delta * 3), max(-3, delta)
        return 0, 0

    def _resolve_model_config(self) -> tuple[str, str | None, str | None]:
        model = str(self._cfg.get("model", "") or "").strip()
        base_url = str(self._cfg.get("base_url", "") or "").strip() or None
        api_key = str(self._cfg.get("api_key", "") or "").strip() or None
        if model and base_url and api_key:
            return model, base_url, api_key

        default_models = get_default_models()
        assist_profiles = get_assist_api_profiles()
        fallback_model = model or str(default_models.get("correction", "") or default_models.get("assist", "")).strip()
        for candidate in ("correction", "deepseek", "gemini", "free"):
            profile = assist_profiles.get(candidate)
            if not isinstance(profile, dict):
                continue
            resolved_model = fallback_model or str(profile.get("model", "") or "").strip()
            resolved_base_url = base_url or str(profile.get("base_url", "") or "").strip() or None
            resolved_api_key = api_key or str(profile.get("api_key", "") or "").strip() or None
            if resolved_model and resolved_base_url and resolved_api_key:
                return resolved_model, resolved_base_url, resolved_api_key
        raise SdkError("剧场模式未找到可用模型配置，请在 plugin.toml 或全局 assist 配置中提供 model/base_url/api_key")

    async def _generate_scene_from_llm(self, user_input: str, state: dict[str, Any]) -> dict[str, Any]:
        model, base_url, api_key = self._resolve_model_config()
        timeout = float(self._cfg.get("timeout_seconds", 30) or 30)
        prompt = (
            f"当前 affection={state['affection']}，mood={state['mood']}。"
            f"用户刚刚说：{user_input.strip() or '...'}。"
            "请输出下一幕剧场场景 JSON。"
        )
        messages = [
            SystemMessage(content=THEATRE_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
        async with create_chat_llm(
            model,
            base_url,
            api_key,
            temperature=1.0,
            streaming=False,
            max_retries=1,
            max_completion_tokens=600,
            timeout=timeout,
        ) as llm:
            response = await asyncio.wait_for(llm.ainvoke(messages), timeout=timeout)
        return self._normalize_scene(response.content, state)

    def _fallback_scene(self, state: dict[str, Any], user_input: str = "") -> dict[str, Any]:
        return {
            "type": SCENE_TYPE,
            "dialogue": "我轻轻抬起眼，像是把没来得及说完的心事藏回呼吸里。再和我说一点吧，我在听。",
            "inner_voice": "只要他的声音还停留在这里，这一幕就不会真正落下。",
            "stage_directions": {
                "motion": "Idle",
                "expression": "neutral",
                "bgm": "default_theatre",
            },
            "stats": {
                "affection": int(state.get("affection", 50) or 50),
                "mood": int(state.get("mood", 0) or 0),
            },
            "meta": {
                "fallback": True,
                "echo": user_input,
            },
        }

    def _normalize_scene(self, raw_content: Any, state: dict[str, Any]) -> dict[str, Any]:
        content = str(raw_content or "").strip()
        payload: dict[str, Any] | None = None
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                payload = parsed
        except Exception:
            match = JSON_BLOCK_RE.search(content)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                    if isinstance(parsed, dict):
                        payload = parsed
                except Exception:
                    payload = None
        if payload is None:
            return self._fallback_scene(state, content)

        stage = payload.get("stage_directions") if isinstance(payload.get("stage_directions"), dict) else {}
        stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
        return {
            "type": SCENE_TYPE,
            "dialogue": str(payload.get("dialogue", "") or "").strip(),
            "inner_voice": str(payload.get("inner_voice", "") or "").strip(),
            "stage_directions": {
                "motion": str(stage.get("motion", "Idle") or "Idle").strip(),
                "expression": str(stage.get("expression", "neutral") or "neutral").strip(),
                "bgm": str(stage.get("bgm", "default_theatre") or "default_theatre").strip(),
            },
            "stats": {
                "affection": int(stats.get("affection", state.get("affection", 50)) or state.get("affection", 50)),
                "mood": int(stats.get("mood", state.get("mood", 0)) or state.get("mood", 0)),
            },
        }

    def _apply_sentiment(self, scene: dict[str, Any], user_input: str, current_state: dict[str, Any]) -> dict[str, Any]:
        affection_delta, mood_delta = self._score_user_sentiment(user_input)
        base_affection = int(scene.get("stats", {}).get("affection", current_state["affection"]))
        base_mood = int(scene.get("stats", {}).get("mood", current_state["mood"]))
        next_state = {
            "affection": self._clamp(base_affection + affection_delta, "min_affection", "max_affection", 0, 100),
            "mood": self._clamp(base_mood + mood_delta, "min_mood", "max_mood", -10, 10),
        }
        saved = self._save_state(next_state)
        scene["stats"] = {
            "affection": saved["affection"],
            "mood": saved["mood"],
        }
        return scene

    def _make_summary(self, scene: dict[str, Any]) -> str:
        return "\n".join([
            f"台词: {scene.get('dialogue', '')}",
            f"独白: {scene.get('inner_voice', '')}",
            f"动作: {scene.get('stage_directions', {}).get('motion', '')}",
            f"表情: {scene.get('stage_directions', {}).get('expression', '')}",
            f"BGM: {scene.get('stage_directions', {}).get('bgm', '')}",
            f"好感度: {scene.get('stats', {}).get('affection', 0)}",
            f"心情: {scene.get('stats', {}).get('mood', 0)}",
        ])

    def _broadcast_scene(self, scene: dict[str, Any], target_lanlan: str | None = None) -> None:
        self.push_message(
            source=self.plugin_id,
            message_type=SCENE_TYPE,
            description="剧场模式场景",
            priority=9,
            content=json.dumps(scene, ensure_ascii=False),
            metadata={"scene": scene},
            target_lanlan=target_lanlan,
        )

    @plugin_entry(
        id="run_theatre_scene",
        name="剧场模式场景",
        description="根据用户输入生成一幕 Galgame 风格的剧场场景，并返回结构化 JSON。",
        llm_result_fields=["summary"],
        timeout=40.0,
        input_schema={
            "type": "object",
            "properties": {
                "user_input": {"type": "string", "description": "用户输入文本"},
                "push_to_main": {"type": "boolean", "default": True, "description": "是否推送到主页面覆盖层"},
                "target_lanlan": {"type": "string", "description": "目标角色名，可选"},
            },
            "required": ["user_input"],
        },
    )
    async def run_theatre_scene(self, user_input: str, push_to_main: bool = True, target_lanlan: str | None = None, **_):
        if not str(user_input or "").strip():
            return Err(SdkError("user_input 不能为空"))
        state = self._load_state()
        try:
            scene = await self._generate_scene_from_llm(user_input, state)
        except Exception as exc:
            self.logger.warning("TheatreMode LLM generation failed: {}", exc)
            scene = self._fallback_scene(state, user_input)
        scene = self._apply_sentiment(scene, user_input, state)
        scene.setdefault("type", SCENE_TYPE)
        summary = self._make_summary(scene)
        if push_to_main:
            self._broadcast_scene(scene, target_lanlan=target_lanlan)
        return Ok({
            "scene": scene,
            "summary": summary,
            "type": SCENE_TYPE,
            "dialogue": scene.get("dialogue", ""),
            "inner_voice": scene.get("inner_voice", ""),
            "stage_directions": scene.get("stage_directions", {}),
            "stats": scene.get("stats", {}),
        })

    @plugin_entry(
        id="get_theatre_state",
        name="剧场模式状态",
        description="读取当前剧场模式的 affection 与 mood 状态。",
        input_schema={"type": "object", "properties": {}},
    )
    async def get_theatre_state(self, **_):
        return Ok(self._load_state())
