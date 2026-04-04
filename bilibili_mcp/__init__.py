from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from plugin.sdk.plugin import NekoPluginBase, neko_plugin, plugin_entry, lifecycle, Ok, Err, SdkError

from .native_service import BilibiliNativeService


@neko_plugin
class BilibiliMCPPlugin(NekoPluginBase):
    DEFAULT_CREDENTIAL_FILE = "bili_credential.json"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.file_logger = self.enable_file_logging(log_level="INFO")
        self.logger = self.file_logger
        self._cfg: Dict[str, Any] = {}
        self._service = BilibiliNativeService(Path(__file__).resolve().parent, self.logger)

    @lifecycle(id="startup")
    async def startup(self, **_):
        cfg = await self.config.dump(timeout=5.0)
        cfg = cfg if isinstance(cfg, dict) else {}
        self._cfg = cfg.get("bilibili_mcp", {}) if isinstance(cfg.get("bilibili_mcp"), dict) else {}
        credential_file = self._cfg.get("credential_file")
        if isinstance(credential_file, str) and credential_file.strip():
            self._service.credential_file = Path(credential_file.strip()).expanduser()
        return Ok({
            "status": "ready",
            "credential_file": str(self._service.credential_file),
            "logged_in": self._service.load_credential() is not None,
        })

    @lifecycle(id="shutdown")
    async def shutdown(self, **_):
        self._service.clear_qr_artifacts()
        return Ok({"status": "shutdown"})

    def _extract_text_items(self, payload: object) -> List[str]:
        if isinstance(payload, str) and payload.strip():
            return [payload.strip()]
        if not isinstance(payload, dict):
            return []
        texts: List[str] = []
        for key in ("message", "next_step", "status"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                texts.append(value.strip())
        return texts

    def _extract_login_qr_png(self, payload: object) -> Optional[bytes]:
        if not isinstance(payload, dict):
            return None
        qrcode_image = payload.get("qrcode_image")
        if not isinstance(qrcode_image, str) or not qrcode_image.startswith("data:image/png;base64,"):
            return None
        encoded = qrcode_image.split(",", 1)[1]
        try:
            return base64.b64decode(encoded)
        except Exception:
            self.logger.debug("Failed to decode bilibili login QR image", exc_info=True)
            return None

    async def _export_login_qr(self, payload: object, run_id: Optional[str]) -> None:
        if not run_id:
            return
        png_data = self._extract_login_qr_png(payload)
        if not png_data:
            return
        export_result = await self.ctx.export_push(
            export_type="binary",
            run_id=run_id,
            binary_data=png_data,
            mime="image/png",
            description="Bilibili login QR code",
            label="bilibili_login_qrcode",
            metadata={"kind": "bilibili_login_qrcode"},
            timeout=10.0,
        )
        if self.logger:
            self.logger.info("Exported bilibili login QR: run_id={}, result={}", run_id, export_result)

    def _summarize_payload(self, payload: object) -> str:
        if isinstance(payload, dict):
            texts = self._extract_text_items(payload)
            if texts:
                return "\n".join(texts[:3])
            if "message" in payload:
                return str(payload.get("message"))
        return json.dumps(payload, ensure_ascii=False) if not isinstance(payload, str) else payload

    def _ok(self, payload: Dict[str, Any]) -> Ok:
        return Ok({"summary": self._summarize_payload(payload), "result": payload})

    def _err(self, exc: Exception) -> Err:
        return Err(SdkError(str(exc)))

    @plugin_entry(
        id="bili_search",
        name="搜索 B 站",
        description="搜索 B 站内容。",
        llm_result_fields=["summary"],
        input_schema={
            "type": "object",
            "properties": {
                "keyword": {"type": "string"},
                "num": {"type": "integer", "default": 10},
                "order": {"type": "string", "default": "totalrank"},
            },
            "required": ["keyword"],
        },
    )
    async def bili_search(self, keyword: str, num: int = 10, order: str = "totalrank", **_):
        try:
            return self._ok(await self._service.search_videos(keyword=keyword, num=num, order=order))
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_video_info",
        name="获取视频信息",
        description="根据 bvid 或 aid 获取 B 站视频详情。",
        llm_result_fields=["summary"],
        input_schema={
            "type": "object",
            "properties": {
                "bvid": {"type": "string"},
                "aid": {"type": "integer"},
            },
        },
    )
    async def bili_video_info(self, bvid: Optional[str] = None, aid: Optional[int] = None, **_):
        if not bvid and aid is None:
            return Err(SdkError("bvid or aid is required"))
        try:
            return self._ok(await self._service.video_info(bvid=bvid, aid=aid))
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_comments",
        name="获取评论",
        description="根据视频 BV 号或关键词获取视频评论。",
        llm_result_fields=["summary"],
        input_schema={
            "type": "object",
            "properties": {
                "bvid": {"type": "string"},
                "keyword": {"type": "string"},
                "num": {"type": "integer", "default": 30},
            },
        },
    )
    async def bili_comments(self, bvid: Optional[str] = None, keyword: Optional[str] = None, num: int = 30, **_):
        if not bvid and not keyword:
            return Err(SdkError("bvid or keyword is required"))
        try:
            if isinstance(bvid, str) and bvid.strip():
                return self._ok(await self._service.comments(bvid=bvid.strip(), num=num))
            return self._ok(await self._service.comments_by_keyword(keyword=keyword or "", num=num))
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_subtitle",
        name="获取字幕",
        description="根据视频 BV 号或关键词获取 B 站字幕；传 keyword 时会自动搜索首个命中视频。",
        llm_result_fields=["summary"],
        input_schema={
            "type": "object",
            "properties": {
                "bvid": {"type": "string"},
                "keyword": {"type": "string"},
            },
        },
    )
    async def bili_subtitle(self, bvid: Optional[str] = None, keyword: Optional[str] = None, **_):
        if not bvid and not keyword:
            return Err(SdkError("bvid or keyword is required"))
        try:
            if isinstance(bvid, str) and bvid.strip():
                return self._ok(await self._service.subtitle(bvid=bvid.strip()))
            return self._ok(await self._service.subtitle_by_keyword(keyword=keyword or ""))
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_danmaku",
        name="获取弹幕",
        description="根据视频 BV 号或关键词获取 B 站弹幕；传 keyword 时会自动搜索首个命中视频。",
        llm_result_fields=["summary"],
        input_schema={
            "type": "object",
            "properties": {
                "bvid": {"type": "string"},
                "keyword": {"type": "string"},
                "num": {"type": "integer", "default": 100},
            },
        },
    )
    async def bili_danmaku(self, bvid: Optional[str] = None, keyword: Optional[str] = None, num: int = 100, **_):
        if not bvid and not keyword:
            return Err(SdkError("bvid or keyword is required"))
        try:
            if isinstance(bvid, str) and bvid.strip():
                return self._ok(await self._service.danmaku(bvid=bvid.strip(), num=num))
            return self._ok(await self._service.danmaku_by_keyword(keyword=keyword or "", num=num))
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_video_zones",
        name="获取视频分区",
        description="获取 B 站常用视频分区列表。",
        llm_result_fields=["summary"],
        input_schema={"type": "object", "properties": {}},
    )
    async def bili_video_zones(self, **_):
        try:
            return self._ok(await self._service.video_zones())
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_hot_buzzwords",
        name="获取热搜词",
        description="获取 B 站热搜关键词。",
        llm_result_fields=["summary"],
        input_schema={
            "type": "object",
            "properties": {
                "page_num": {"type": "integer", "default": 1},
                "page_size": {"type": "integer", "default": 20},
            },
        },
    )
    async def bili_hot_buzzwords(self, page_num: int = 1, page_size: int = 20, **_):
        try:
            return self._ok(await self._service.hot_buzzwords(page_num=page_num, page_size=page_size))
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_weekly_hot",
        name="获取每周必看",
        description="获取 B 站每周必看列表或指定期内容。",
        llm_result_fields=["summary"],
        input_schema={
            "type": "object",
            "properties": {
                "week": {"type": "integer", "default": 0},
            },
        },
    )
    async def bili_weekly_hot(self, week: int = 0, **_):
        try:
            return self._ok(await self._service.weekly_hot(week=week))
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_rank",
        name="获取排行榜",
        description="获取 B 站各分区排行榜。",
        llm_result_fields=["summary"],
        input_schema={
            "type": "object",
            "properties": {
                "category": {"type": "string", "default": "all"},
                "day": {"type": "integer", "default": 3},
            },
        },
    )
    async def bili_rank(self, category: str = "all", day: int = 3, **_):
        try:
            return self._ok(await self._service.rank_videos(category=category, day=day))
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_user_info",
        name="获取用户信息",
        description="根据 UID 获取 B 站用户信息。",
        llm_result_fields=["summary"],
        input_schema={
            "type": "object",
            "properties": {
                "uid": {"type": "integer"},
            },
            "required": ["uid"],
        },
    )
    async def bili_user_info(self, uid: int, **_):
        try:
            return self._ok(await self._service.user_info(uid=uid))
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_user_videos",
        name="获取用户视频",
        description="根据 UID 获取 B 站用户投稿视频列表。",
        llm_result_fields=["summary"],
        input_schema={
            "type": "object",
            "properties": {
                "uid": {"type": "integer"},
                "pn": {"type": "integer", "default": 1},
                "ps": {"type": "integer", "default": 30},
                "order": {"type": "string", "default": "pubdate"},
                "keyword": {"type": "string", "default": ""},
            },
            "required": ["uid"],
        },
    )
    async def bili_user_videos(self, uid: int, pn: int = 1, ps: int = 30, order: str = "pubdate", keyword: str = "", **_):
        try:
            return self._ok(await self._service.user_videos(uid=uid, pn=pn, ps=ps, order=order, keyword=keyword))
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_favorite_lists",
        name="获取收藏夹列表",
        description="获取当前用户或指定 UID 的收藏夹列表。",
        llm_result_fields=["summary"],
        input_schema={
            "type": "object",
            "properties": {
                "uid": {"type": "integer", "default": 0},
            },
        },
    )
    async def bili_favorite_lists(self, uid: int = 0, **_):
        try:
            return self._ok(await self._service.favorite_lists(uid=uid))
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_favorite_content",
        name="获取收藏夹内容",
        description="获取指定收藏夹中的视频列表。",
        llm_result_fields=["summary"],
        input_schema={
            "type": "object",
            "properties": {
                "media_id": {"type": "integer"},
                "page": {"type": "integer", "default": 1},
                "keyword": {"type": "string", "default": ""},
            },
            "required": ["media_id"],
        },
    )
    async def bili_favorite_content(self, media_id: int, page: int = 1, keyword: str = "", **_):
        try:
            return self._ok(await self._service.favorite_content(media_id=media_id, page=page, keyword=keyword))
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_unread_messages",
        name="获取未读消息",
        description="获取 B 站未读消息统计。",
        llm_result_fields=["summary"],
        input_schema={"type": "object", "properties": {}},
    )
    async def bili_unread_messages(self, **_):
        try:
            return self._ok(await self._service.unread_messages())
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_received_replies",
        name="获取收到的回复",
        description="获取最近收到的评论回复通知。",
        llm_result_fields=["summary"],
        input_schema={"type": "object", "properties": {}},
    )
    async def bili_received_replies(self, **_):
        try:
            return self._ok(await self._service.received_replies())
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_received_at_and_likes",
        name="获取收到的@和点赞",
        description="获取最近收到的 @ 提及和点赞通知。",
        llm_result_fields=["summary"],
        input_schema={"type": "object", "properties": {}},
    )
    async def bili_received_at_and_likes(self, **_):
        try:
            return self._ok(await self._service.received_at_and_likes())
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_reply",
        name="回复评论",
        description="在 B 站视频下发表评论或回复评论。需要已登录。",
        llm_result_fields=["summary"],
        input_schema={
            "type": "object",
            "properties": {
                "bvid": {"type": "string"},
                "text": {"type": "string"},
                "rpid": {"type": "integer", "default": 0},
                "root": {"type": "integer", "default": 0},
            },
            "required": ["bvid", "text"],
        },
    )
    async def bili_reply(self, bvid: str, text: str, rpid: int = 0, root: int = 0, **_):
        try:
            return self._ok(await self._service.reply(bvid=bvid, text=text, rpid=rpid, root=root))
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_crawl",
        name="批量采集",
        description="按关键词批量采集 B 站视频、评论和字幕。",
        llm_result_fields=["summary"],
        input_schema={
            "type": "object",
            "properties": {
                "keyword": {"type": "string"},
                "max_videos": {"type": "integer", "default": 5},
                "comments_per_video": {"type": "integer", "default": 20},
                "get_subtitles": {"type": "boolean", "default": True},
            },
            "required": ["keyword"],
        },
    )
    async def bili_crawl(self, keyword: str, max_videos: int = 5, comments_per_video: int = 20, get_subtitles: bool = True, **_):
        try:
            return self._ok(await self._service.crawl(keyword=keyword, max_videos=max_videos, comments_per_video=comments_per_video, get_subtitles=get_subtitles))
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_hot_videos",
        name="获取热门视频",
        description="获取 B 站热门视频列表。",
        llm_result_fields=["summary"],
        input_schema={
            "type": "object",
            "properties": {
                "pn": {"type": "integer", "default": 1},
                "ps": {"type": "integer", "default": 20},
            },
        },
    )
    async def bili_hot_videos(self, pn: int = 1, ps: int = 20, **_):
        try:
            return self._ok(await self._service.hot_videos(pn=pn, ps=ps))
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_check_credential",
        name="检查 B 站凭证",
        description="检查 bilibili 登录凭证是否可用。",
        llm_result_fields=["summary"],
        input_schema={"type": "object", "properties": {}},
    )
    async def bili_check_credential(self, **_):
        try:
            return self._ok(await self._service.check_credential())
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_login",
        name="获取登录二维码",
        description="生成 B 站扫码登录二维码。",
        llm_result_fields=["summary"],
        input_schema={"type": "object", "properties": {}},
    )
    async def bili_login(self, _ctx: Optional[Dict[str, Any]] = None, **_):
        try:
            payload = await self._service.login()
            if payload.get("status") == "qrcode_ready":
                try:
                    self._service.open_qr_in_browser()
                except Exception:
                    self.logger.exception("Failed to open bilibili login QR in browser")
            run_id = _ctx.get("run_id") if isinstance(_ctx, dict) else None
            try:
                await self._export_login_qr(payload, run_id if isinstance(run_id, str) else None)
            except Exception:
                self.logger.exception("Failed to export bilibili login QR image")
            return self._ok(payload)
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_login_check",
        name="检查登录状态",
        description="检查当前登录状态。",
        llm_result_fields=["summary"],
        input_schema={"type": "object", "properties": {}},
    )
    async def bili_login_check(self, **_):
        try:
            return self._ok(await self._service.login_check())
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_send_dynamic",
        name="发布动态",
        description="发布 B 站动态。需要已登录。",
        llm_result_fields=["summary"],
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "images": {"type": "array", "items": {"type": "string"}},
                "topic_id": {"type": "integer", "default": 0},
                "schedule_time": {"type": "integer", "default": 0},
            },
            "required": ["text"],
        },
    )
    async def bili_send_dynamic(self, text: str, images: Optional[List[str]] = None, topic_id: int = 0, schedule_time: int = 0, **_):
        try:
            return self._ok(await self._service.send_dynamic(text=text, images=images, topic_id=topic_id, schedule_time=schedule_time))
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_send_message",
        name="发送私信",
        description="向指定用户发送私信。需要已登录。",
        llm_result_fields=["summary"],
        input_schema={
            "type": "object",
            "properties": {
                "receiver_uid": {"type": "integer"},
                "text": {"type": "string"},
            },
            "required": ["receiver_uid", "text"],
        },
    )
    async def bili_send_message(self, receiver_uid: int, text: str, **_):
        try:
            return self._ok(await self._service.send_message(receiver_uid=receiver_uid, text=text))
        except Exception as e:
            return self._err(e)

    @plugin_entry(
        id="bili_list_mcp_tools",
        name="列出 Bilibili 能力",
        description="列出当前原生 bilibili 插件暴露的能力。",
        llm_result_fields=["total"],
        input_schema={"type": "object", "properties": {}},
    )
    async def bili_list_mcp_tools(self, **_):
        tools = [
            "bili_check_credential",
            "bili_login",
            "bili_login_check",
            "bili_search",
            "bili_hot_videos",
            "bili_video_info",
            "bili_comments",
            "bili_subtitle",
            "bili_danmaku",
            "bili_video_zones",
            "bili_hot_buzzwords",
            "bili_weekly_hot",
            "bili_rank",
            "bili_user_info",
            "bili_user_videos",
            "bili_favorite_lists",
            "bili_favorite_content",
            "bili_unread_messages",
            "bili_received_replies",
            "bili_received_at_and_likes",
            "bili_reply",
            "bili_crawl",
            "bili_send_dynamic",
            "bili_send_message",
        ]
        return Ok({"total": len(tools), "tools": tools, "native": True})
