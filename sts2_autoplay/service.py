from __future__ import annotations

import asyncio
import random
import time
from collections import deque
from typing import Any, Awaitable, Callable, Deque, Dict, Optional

from .client import STS2ApiClient, STS2ClientError
from .models import normalize_snapshot


class STS2AutoplayService:
    def __init__(self, logger, status_reporter: Callable[[dict[str, Any]], None], frontend_notifier: Optional[Callable[..., Any]] = None) -> None:
        self.logger = logger
        self._report_status = status_reporter
        self._frontend_notifier = frontend_notifier
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
        self._step_lock = asyncio.Lock()

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
            except asyncio.CancelledError:
                pass
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
        context = await self._fetch_step_context(publish=True, record_history=True)
        return {"status": "ok", "message": f"已刷新状态，screen={self._snapshot.get('screen')}", "snapshot": context["snapshot"]}

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
        async with self._step_lock:
            return await self._step_once_locked()

    async def _step_once_locked(self) -> Dict[str, Any]:
        context = await self._await_stable_step_context()
        actions = context["actions"]
        if not actions:
            snapshot = context["snapshot"]
            return {"status": "idle", "message": "当前没有可执行动作", "snapshot": snapshot}
        action = self._select_action(actions)
        prepared = self._prepare_action_request(action, context)
        revalidated = await self._revalidate_prepared_action(prepared, context)
        if revalidated is None:
            context = await self._await_stable_step_context()
            actions = context["actions"]
            if not actions:
                snapshot = context["snapshot"]
                return {"status": "idle", "message": "当前没有可执行动作", "snapshot": snapshot}
            action = self._select_action(actions)
            prepared = self._prepare_action_request(action, context)
        result = await self._execute_action(prepared)
        await self._maybe_emit_frontend_message(
            event_type="action",
            action=prepared.get("action_type"),
            snapshot=context.get("snapshot") if isinstance(context.get("snapshot"), dict) else {},
            detail=result.get("message") or "",
        )
        await self._await_action_interval()
        settled_context = await self._await_post_action_settle(context, prepared)
        self._publish_snapshot(settled_context["snapshot"], record_history=True)
        return {**result, "snapshot": settled_context["snapshot"]}

    def _publish_snapshot(self, snapshot: Dict[str, Any], *, record_history: bool) -> Dict[str, Any]:
        self._snapshot = snapshot
        self._server_state = "connected"
        self._last_error = ""
        self._last_poll_at = time.time()
        if record_history:
            self._history.appendleft({
                "type": "snapshot",
                "time": self._last_poll_at,
                "screen": self._snapshot.get("screen"),
                "available_actions": self._snapshot.get("available_action_count", 0),
            })
        self._emit_status()
        return snapshot

    async def _fetch_step_context(self, *, publish: bool = False, record_history: bool = False) -> Dict[str, Any]:
        client = self._require_client()
        state_payload = await client.get_state()
        actions_payload = await client.get_available_actions()
        snapshot = normalize_snapshot(state_payload, actions_payload)
        if publish:
            self._publish_snapshot(snapshot, record_history=record_history)
        return {
            "snapshot": snapshot,
            "actions": snapshot.get("available_actions") if isinstance(snapshot.get("available_actions"), list) else [],
            "signature": self._snapshot_signature(snapshot),
            "action_signature": self._action_signature(snapshot),
            "state_signature": self._state_signature(snapshot),
            "captured_at": time.time(),
        }

    def _snapshot_signature(self, snapshot: dict[str, Any]) -> tuple[Any, ...]:
        return (
            snapshot.get("screen"),
            snapshot.get("floor"),
            snapshot.get("act"),
            bool(snapshot.get("in_combat", False)),
            snapshot.get("available_action_count", 0),
            self._action_signature(snapshot),
            self._state_signature(snapshot),
        )

    def _action_signature(self, snapshot: dict[str, Any]) -> tuple[tuple[Any, ...], ...]:
        actions = snapshot.get("available_actions") if isinstance(snapshot.get("available_actions"), list) else []
        return tuple(self._action_fingerprint(action) for action in actions if isinstance(action, dict))

    def _action_fingerprint(self, action: dict[str, Any]) -> tuple[Any, ...]:
        raw = action.get("raw") if isinstance(action.get("raw"), dict) else {}
        return (
            str(action.get("type") or raw.get("type") or raw.get("name") or raw.get("action") or ""),
            raw.get("option_index"),
            raw.get("index"),
            raw.get("card_index"),
            raw.get("target_index"),
            raw.get("name"),
        )

    def _state_signature(self, snapshot: dict[str, Any]) -> tuple[Any, ...]:
        raw_state = snapshot.get("raw_state") if isinstance(snapshot.get("raw_state"), dict) else {}
        combat = raw_state.get("combat") if isinstance(raw_state.get("combat"), dict) else {}
        hand = combat.get("hand") if isinstance(combat.get("hand"), list) else []
        run = raw_state.get("run") if isinstance(raw_state.get("run"), dict) else {}
        potions = run.get("potions") if isinstance(run.get("potions"), list) else []
        hand_signature = tuple(
            (
                card.get("index"),
                card.get("uuid"),
                card.get("id"),
                card.get("name"),
                bool(card.get("playable")),
                tuple(card.get("valid_target_indices")) if isinstance(card.get("valid_target_indices"), list) else (),
            )
            for card in hand
            if isinstance(card, dict)
        )
        potion_signature = tuple(
            (
                potion.get("index"),
                potion.get("id"),
                potion.get("name"),
                bool(potion.get("can_use")),
                bool(potion.get("can_discard")),
            )
            for potion in potions
            if isinstance(potion, dict)
        )
        return (
            raw_state.get("screen"),
            raw_state.get("screen_type"),
            raw_state.get("floor"),
            raw_state.get("act_floor"),
            raw_state.get("act"),
            raw_state.get("turn"),
            raw_state.get("turn_count"),
            raw_state.get("phase"),
            bool(raw_state.get("in_combat", False)),
            combat.get("turn"),
            combat.get("turn_count"),
            combat.get("player_energy"),
            combat.get("end_turn_available"),
            hand_signature,
            potion_signature,
        )

    def _is_actionable_context(self, context: dict[str, Any]) -> bool:
        return bool(context["actions"])

    def _is_transitional_context(self, context: dict[str, Any]) -> bool:
        snapshot = context["snapshot"]
        raw_state = snapshot.get("raw_state") if isinstance(snapshot.get("raw_state"), dict) else {}
        screen = self._normalized_screen_name(snapshot)
        in_combat = bool(snapshot.get("in_combat", False) or raw_state.get("in_combat", False))
        if context["actions"]:
            return False
        if in_combat:
            return screen == "combat"
        return self._is_eventish_screen(screen)

    def _normalized_screen_name(self, snapshot: dict[str, Any]) -> str:
        raw_state = snapshot.get("raw_state") if isinstance(snapshot.get("raw_state"), dict) else {}
        screen = snapshot.get("screen") or raw_state.get("screen") or raw_state.get("screen_type") or ""
        return str(screen).strip().lower()

    def _is_eventish_screen(self, screen: str) -> bool:
        normalized = (screen or "").strip().lower()
        if not normalized:
            return False
        return any(keyword in normalized for keyword in {"event", "modal", "overlay", "dialog", "choice"})

    async def _await_stable_step_context(self) -> Dict[str, Any]:
        attempts = max(2, int(self._cfg.get("stable_state_attempts", 4) or 4))
        delay = max(0.1, float(self._cfg.get("poll_interval_active_seconds", 1) or 1) / 2)
        previous: Optional[Dict[str, Any]] = None
        last_context: Optional[Dict[str, Any]] = None
        for attempt in range(attempts):
            context = await self._fetch_step_context(publish=(attempt == 0), record_history=(attempt == 0))
            last_context = context
            if previous is not None and context["signature"] == previous["signature"]:
                return context
            if self._is_actionable_context(context) and not self._is_transitional_context(context):
                return context
            if not self._is_transitional_context(context) and attempt == attempts - 1:
                return context
            previous = context
            if attempt < attempts - 1:
                await asyncio.sleep(delay)
        return last_context or await self._fetch_step_context(publish=True, record_history=True)

    def _prepare_action_request(self, action: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        raw = action.get("raw") if isinstance(action.get("raw"), dict) else {}
        raw_action = raw.get("action")
        action_type = str(action.get("type") or raw.get("type") or (raw_action if isinstance(raw_action, str) else ""))
        kwargs = self._normalize_action_kwargs(action_type, raw, context)
        return {
            "action": action,
            "action_type": action_type,
            "kwargs": kwargs,
            "fingerprint": self._action_fingerprint(action),
            "context_signature": context["signature"],
        }

    async def _revalidate_prepared_action(self, prepared: dict[str, Any], context: dict[str, Any]) -> Optional[dict[str, Any]]:
        actions = context["actions"]
        if not any(self._action_fingerprint(action) == prepared["fingerprint"] for action in actions if isinstance(action, dict)):
            return None
        latest = await self._fetch_step_context()
        if any(self._action_fingerprint(action) == prepared["fingerprint"] for action in latest["actions"] if isinstance(action, dict)):
            return prepared
        return None

    async def _await_action_interval(self) -> None:
        delay = max(0.0, float(self._cfg.get("action_interval_seconds", 0.5) or 0.5))
        if delay > 0:
            await asyncio.sleep(delay)

    async def _await_post_action_settle(self, before_context: dict[str, Any], prepared: dict[str, Any]) -> Dict[str, Any]:
        attempts = max(2, int(self._cfg.get("post_action_settle_attempts", 6) or 6))
        delay = max(0.1, float(self._cfg.get("post_action_delay_seconds", 0.5) or 0.5))
        last_context = before_context
        for attempt in range(attempts):
            if attempt > 0:
                await asyncio.sleep(delay)
            context = await self._fetch_step_context()
            last_context = context
            if context["signature"] != before_context["signature"]:
                if not self._is_transitional_context(context):
                    return context
                continue
            if not any(self._action_fingerprint(action) == prepared["fingerprint"] for action in context["actions"] if isinstance(action, dict)):
                return context
        return last_context

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
            except asyncio.CancelledError:
                pass
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
        if strategy not in {"heuristic", "defect"}:
            raise RuntimeError(f"暂不支持策略: {strategy}")
        self._cfg["strategy"] = strategy
        self._emit_status()
        return {"status": "ok", "message": f"策略已切换为 {strategy}", "strategy": strategy}

    async def set_speed(self, *, action_interval_seconds: Optional[float] = None, post_action_delay_seconds: Optional[float] = None, poll_interval_active_seconds: Optional[float] = None) -> Dict[str, Any]:
        if action_interval_seconds is not None:
            self._cfg["action_interval_seconds"] = max(0.0, float(action_interval_seconds))
        if post_action_delay_seconds is not None:
            self._cfg["post_action_delay_seconds"] = max(0.0, float(post_action_delay_seconds))
        if poll_interval_active_seconds is not None:
            self._cfg["poll_interval_active_seconds"] = max(0.1, float(poll_interval_active_seconds))
        return {
            "status": "ok",
            "message": "速度设置已更新",
            "action_interval_seconds": self._cfg.get("action_interval_seconds"),
            "post_action_delay_seconds": self._cfg.get("post_action_delay_seconds"),
            "poll_interval_active_seconds": self._cfg.get("poll_interval_active_seconds"),
        }

    async def _maybe_emit_frontend_message(self, *, event_type: str, snapshot: Optional[Dict[str, Any]] = None, action: Optional[str] = None, detail: str = "", priority: int = 5, force: bool = False) -> None:
        notifier = self._frontend_notifier
        if notifier is None:
            return
        if not bool(self._cfg.get("llm_frontend_output_enabled", False)):
            return
        probability = self._clamp_probability(self._cfg.get("llm_frontend_output_probability", 0.15))
        if not force and probability <= 0.0:
            return
        if not force and random.random() > probability:
            return
        snapshot_data = snapshot if isinstance(snapshot, dict) else {}
        screen = str(snapshot_data.get("screen") or "unknown")
        floor = snapshot_data.get("floor") or 0
        act = snapshot_data.get("act") or 0
        if event_type == "action":
            action_name = str(action or "unknown")
            content = f"尖塔自动游玩执行了动作：{action_name}（screen={screen}, floor={floor}）"
            description = f"尖塔动作：{action_name}"
        elif event_type == "error":
            content = f"尖塔自动游玩出错：{detail or self._last_error or 'unknown error'}"
            description = "尖塔自动游玩错误"
            action_name = str(action or "")
        else:
            return
        metadata = {
            "plugin_id": "sts2_autoplay",
            "event_type": event_type,
            "action": action_name,
            "screen": screen,
            "floor": floor,
            "act": act,
        }
        try:
            maybe_awaitable = notifier(content=content, description=description, metadata=metadata, priority=priority)
            if isinstance(maybe_awaitable, Awaitable):
                await maybe_awaitable
        except Exception as exc:
            self.logger.warning(f"frontend notification failed: {exc}")

    def _clamp_probability(self, value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except Exception:
            return 0.0

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
            await self._maybe_emit_frontend_message(event_type="error", detail=str(exc), snapshot=self._snapshot, priority=7, force=True)
            self._emit_status()

    def _select_action(self, actions: list[dict[str, Any]]) -> dict[str, Any]:
        preferred_order = [
            "confirm_modal",
            "dismiss_modal",
            "choose_event_option",
            "proceed",
            "choose_map_node",
            "choose_treasure_relic",
            "play_card",
            "end_turn",
            "use_potion",
            "discard_potion",
        ]
        for action_type in preferred_order:
            for action in actions:
                if str(action.get("type") or "") == action_type:
                    return action
        for action in actions:
            action_type = str(action.get("type") or "")
            if action_type and action_type not in {"wait", "noop"}:
                return action
        return actions[0]

    async def _execute_action(self, prepared: dict[str, Any]) -> Dict[str, Any]:
        client = self._require_client()
        action_type = str(prepared.get("action_type") or "")
        kwargs = prepared.get("kwargs") if isinstance(prepared.get("kwargs"), dict) else {}
        result = await client.execute_action(action_type, **kwargs)
        self._last_action = action_type
        self._last_action_at = time.time()
        self._history.appendleft({"type": "action", "time": self._last_action_at, "action": action_type, "result": result, "kwargs": kwargs})
        self._emit_status()
        return {"status": "ok", "message": f"已执行动作: {action_type}", "action": action_type, "result": result}

    def _normalize_action_kwargs(self, action_type: str, raw: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        kwargs = {
            k: v
            for k, v in raw.items()
            if k not in {"type", "name", "label", "description", "requires_target", "requires_index"}
            and not (k == "action" and isinstance(v, dict))
        }
        if "option_index" not in kwargs and "index" not in kwargs and "card_index" not in kwargs and bool(raw.get("requires_index")):
            if action_type == "discard_potion":
                kwargs["option_index"] = self._find_discardable_potion_index(context)
            elif action_type in {"choose_map_node", "choose_treasure_relic", "choose_event_option", "choose_rest_option", "select_deck_card", "buy_card", "buy_relic", "buy_potion"}:
                preferred_option_index = self._find_preferred_card_option_index(raw, context)
                if preferred_option_index is None:
                    preferred_option_index = self._find_preferred_character_option_index(raw, context)
                kwargs["option_index"] = preferred_option_index if preferred_option_index is not None else 0
            elif action_type == "use_potion":
                kwargs["option_index"] = self._find_usable_potion_index(context)
            elif action_type == "play_card":
                kwargs["card_index"] = self._find_playable_card_index(context)
                target_index = self._find_card_target_index(context, kwargs["card_index"])
                if target_index is not None:
                    kwargs["target_index"] = target_index
            else:
                kwargs["index"] = 0
        return kwargs

    def _find_preferred_card_option_index(self, raw: dict[str, Any], context: dict[str, Any]) -> Optional[int]:
        if str(self._cfg.get("strategy") or "heuristic").strip().lower() != "defect":
            return None
        if not self._is_card_reward_context(raw, context):
            return None
        options = self._card_reward_options(raw, context)
        if not options:
            return None
        best_option: Optional[dict[str, Any]] = None
        best_score: Optional[int] = None
        for option in options:
            score = self._score_defect_card_option(option, context)
            if best_score is None or score > best_score:
                best_option = option
                best_score = score
        if best_option is None or best_score is None or best_score <= 0:
            return None
        return best_option["index"]

    def _is_card_reward_context(self, raw: dict[str, Any], context: dict[str, Any]) -> bool:
        snapshot = context.get("snapshot") if isinstance(context.get("snapshot"), dict) else {}
        raw_state = snapshot.get("raw_state") if isinstance(snapshot.get("raw_state"), dict) else {}
        screen_candidates = {
            self._normalized_screen_name(snapshot),
            str(raw_state.get("screen") or "").strip().lower(),
            str(raw_state.get("screen_type") or "").strip().lower(),
        }
        if any(keyword in candidate for candidate in screen_candidates for keyword in {"reward", "card reward", "card", "combat reward"} if candidate):
            return True
        return bool(self._card_reward_options(raw, context))

    def _card_reward_options(self, raw: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        for candidate in self._iter_option_candidates(raw):
            options = self._extract_card_reward_options(candidate)
            if options:
                return options
        for action in context.get("actions", []):
            if not isinstance(action, dict):
                continue
            raw_action = action.get("raw") if isinstance(action.get("raw"), dict) else {}
            for candidate in self._iter_option_candidates(raw_action):
                options = self._extract_card_reward_options(candidate)
                if options:
                    return options
        return []

    def _iter_option_candidates(self, raw: dict[str, Any]) -> list[Any]:
        return [
            raw,
            raw.get("action") if isinstance(raw.get("action"), dict) else None,
            raw.get("options"),
            raw.get("choices"),
            raw.get("cards"),
            raw.get("items"),
            raw.get("rewards"),
        ]

    def _extract_card_reward_options(self, candidate: Any) -> list[dict[str, Any]]:
        if isinstance(candidate, list):
            options: list[dict[str, Any]] = []
            for idx, item in enumerate(candidate):
                if not isinstance(item, dict):
                    continue
                texts = self._card_option_texts(item)
                if not texts:
                    continue
                option_index = item.get("option_index")
                if option_index is None:
                    option_index = item.get("index", idx)
                option = {
                    "index": int(option_index),
                    "texts": texts,
                    "raw": item,
                }
                options.append(option)
            return options
        if isinstance(candidate, dict):
            for key in ("options", "choices", "cards", "items", "rewards"):
                nested = candidate.get(key)
                if isinstance(nested, list):
                    return self._extract_card_reward_options(nested)
        return []

    def _card_option_texts(self, item: dict[str, Any]) -> set[str]:
        texts: set[str] = set()
        for key in ("label", "description", "name", "id", "card_id", "card_name", "title"):
            value = item.get(key)
            if value is not None:
                normalized = str(value).strip().lower()
                if normalized:
                    texts.add(normalized)
        card = item.get("card") if isinstance(item.get("card"), dict) else None
        if card is not None:
            texts.update(self._card_option_texts(card))
        return texts

    def _score_defect_card_option(self, option: dict[str, Any], context: dict[str, Any]) -> int:
        texts = option.get("texts") if isinstance(option.get("texts"), set) else set()
        score = 0
        high_priority = {
            "冷头": 100,
            "快速检索": 95,
            "全息影像": 95,
            "暴风雨": 92,
            "冰川": 90,
            "充电": 82,
            "高速脱离": 80,
            "白噪声": 72,
            "引雷针": 94,
            "电流相生": 92,
            "子程序": 96,
            "雷暴": 94,
            "创造性ai": 88,
            "创造性 ai": 88,
            "超临界态": 86,
            "双倍": 84,
            "内核加速": 82,
            "火箭拳": 90,
            "污秽攻击": 74,
            "压缩": 88,
            "羽化": 90,
            "万众一心": 84,
        }
        low_priority = {
            "打击": -25,
            "防御": -10,
            "硬撑": -35,
            "超频": -30,
        }
        for name, value in high_priority.items():
            if any(name in text for text in texts):
                score += value
        for name, value in low_priority.items():
            if any(name in text for text in texts):
                score += value
        if any("状态" in text for text in texts) and not self._defect_has_card(context, {"压缩"}):
            score -= 18
        if any(keyword in text for text in texts for keyword in {"能力", "power"}):
            score += 8
        if any(keyword in text for text in texts for keyword in {"球", "闪电球", "冰球", "充能球", "orb"}):
            score += 10
        return score

    def _defect_has_card(self, context: dict[str, Any], names: set[str]) -> bool:
        raw_state = context.get("snapshot", {}).get("raw_state") if isinstance(context.get("snapshot"), dict) else {}
        for container_key in ("deck", "master_deck", "cards"):
            cards = raw_state.get(container_key)
            if not isinstance(cards, list):
                continue
            for card in cards:
                if not isinstance(card, dict):
                    continue
                card_texts = self._card_option_texts(card)
                if any(any(name in text for text in card_texts) for name in names):
                    return True
        run = raw_state.get("run") if isinstance(raw_state.get("run"), dict) else {}
        deck = run.get("deck") if isinstance(run.get("deck"), list) else []
        for card in deck:
            if not isinstance(card, dict):
                continue
            card_texts = self._card_option_texts(card)
            if any(any(name in text for text in card_texts) for name in names):
                return True
        return False

    def _find_preferred_character_option_index(self, raw: dict[str, Any], context: dict[str, Any]) -> Optional[int]:
        if not self._is_character_select_context(context):
            return None
        preferred_aliases = [
            {"故障机器人", "defect"},
            {"铁血战士", "ironclad"},
        ]
        options = self._character_selection_options(raw, context)
        if not options:
            return None
        for aliases in preferred_aliases:
            for option in options:
                if self._character_option_matches(option, aliases):
                    return option["index"]
        return None

    def _is_character_select_context(self, context: dict[str, Any]) -> bool:
        snapshot = context.get("snapshot") if isinstance(context.get("snapshot"), dict) else {}
        raw_state = snapshot.get("raw_state") if isinstance(snapshot.get("raw_state"), dict) else {}
        screen = self._normalized_screen_name(snapshot)
        text_candidates = {
            screen,
            str(raw_state.get("screen") or "").strip().lower(),
            str(raw_state.get("screen_type") or "").strip().lower(),
        }
        if any(keyword in candidate for candidate in text_candidates for keyword in {"char", "character", "player select", "select"} if candidate):
            return True
        for action in context.get("actions", []):
            if not isinstance(action, dict):
                continue
            raw_action = action.get("raw") if isinstance(action.get("raw"), dict) else {}
            if self._character_selection_options(raw_action, context):
                return True
        return False

    def _character_selection_options(self, raw: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        for candidate in self._iter_option_candidates(raw):
            options = self._extract_character_options(candidate)
            if options:
                return options
        for action in context.get("actions", []):
            if not isinstance(action, dict):
                continue
            raw_action = action.get("raw") if isinstance(action.get("raw"), dict) else {}
            for candidate in self._iter_option_candidates(raw_action):
                options = self._extract_character_options(candidate)
                if options:
                    return options
        return []

    def _extract_character_options(self, candidate: Any) -> list[dict[str, Any]]:
        if isinstance(candidate, list):
            options: list[dict[str, Any]] = []
            for idx, item in enumerate(candidate):
                if not isinstance(item, dict):
                    continue
                option_index = item.get("option_index")
                if option_index is None:
                    option_index = item.get("index", idx)
                option = {
                    "index": int(option_index),
                    "texts": self._character_option_texts(item),
                }
                if option["texts"]:
                    options.append(option)
            return options
        if isinstance(candidate, dict):
            nested_keys = ("options", "choices", "characters", "items")
            for key in nested_keys:
                nested = candidate.get(key)
                if isinstance(nested, list):
                    return self._extract_character_options(nested)
        return []

    def _character_option_texts(self, item: dict[str, Any]) -> set[str]:
        texts: set[str] = set()
        for key in ("label", "description", "name", "id", "character", "character_id", "class", "player_class"):
            value = item.get(key)
            if value is not None:
                normalized = str(value).strip().lower()
                if normalized:
                    texts.add(normalized)
        return texts

    def _character_option_matches(self, option: dict[str, Any], aliases: set[str]) -> bool:
        texts = option.get("texts") if isinstance(option.get("texts"), set) else set()
        return any(alias in texts for alias in aliases)

    def _find_discardable_potion_index(self, context: dict[str, Any]) -> int:
        for potion in self._potions(context):
            if bool(potion.get("can_discard")):
                return int(potion.get("index", 0))
        raise RuntimeError("当前没有可丢弃的药水")

    def _find_usable_potion_index(self, context: dict[str, Any]) -> int:
        for potion in self._potions(context):
            if bool(potion.get("can_use")):
                return int(potion.get("index", 0))
        raise RuntimeError("当前没有可使用的药水")

    def _find_playable_card_index(self, context: dict[str, Any]) -> int:
        combat = self._combat_state(context)
        hand = combat.get("hand") if isinstance(combat.get("hand"), list) else []
        for card in hand:
            if isinstance(card, dict) and bool(card.get("playable")):
                return int(card.get("index", 0))
        raise RuntimeError("当前没有可打出的卡牌")

    def _find_card_target_index(self, context: dict[str, Any], card_index: int) -> Optional[int]:
        combat = self._combat_state(context)
        hand = combat.get("hand") if isinstance(combat.get("hand"), list) else []
        for card in hand:
            if not isinstance(card, dict) or int(card.get("index", -1)) != card_index:
                continue
            valid_target_indices = card.get("valid_target_indices") if isinstance(card.get("valid_target_indices"), list) else []
            if valid_target_indices:
                return int(valid_target_indices[0])
            return None
        return None

    def _combat_state(self, context: dict[str, Any]) -> dict[str, Any]:
        raw_state = context.get("snapshot", {}).get("raw_state") if isinstance(context.get("snapshot"), dict) else {}
        combat = raw_state.get("combat") if isinstance(raw_state, dict) and isinstance(raw_state.get("combat"), dict) else {}
        return combat

    def _potions(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        raw_state = context.get("snapshot", {}).get("raw_state") if isinstance(context.get("snapshot"), dict) else {}
        run = raw_state.get("run") if isinstance(raw_state, dict) and isinstance(raw_state.get("run"), dict) else {}
        potions = run.get("potions") if isinstance(run.get("potions"), list) else []
        return [potion for potion in potions if isinstance(potion, dict)]

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
