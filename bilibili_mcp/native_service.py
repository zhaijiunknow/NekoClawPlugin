from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import random
import struct
import time
import webbrowser
import zlib
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional
from urllib.parse import urlencode

from bilibili_api import Credential, comment, dynamic, favorite_list, hot, rank, search, session, user, video
from bilibili_api.login_v2 import QrCodeLogin, QrCodeLoginEvents
from bilibili_api.utils.picture import Picture

_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

WS_URL = "wss://broadcastlv.chat.bilibili.com/sub"
HEADER_LEN = 16
PROTOCOL_VERSION_HEARTBEAT = 1
PROTOCOL_VERSION_ZLIB = 2
PROTOCOL_VERSION_BROTLI = 3
OPERATION_HEARTBEAT = 2
OPERATION_HEARTBEAT_REPLY = 3
OPERATION_SEND_MSG = 5
OPERATION_AUTH = 7
OPERATION_AUTH_REPLY = 8

_module_logger: Optional[Callable[[str, str], None]] = None


def _get_mixin_key(img_key: str, sub_key: str) -> str:
    if not img_key or not sub_key or len(img_key) != 32 or len(sub_key) != 32:
        return ""
    raw = img_key + sub_key
    return "".join(raw[i] for i in _MIXIN_KEY_ENC_TAB if i < len(raw))[:32]


def _wbi_sign(params: dict, mixin_key: str) -> dict:
    wts = int(time.time())
    params = dict(params)
    params["wts"] = wts
    filtered = {
        k: "".join(c for c in str(v) if c not in "!'()*")
        for k, v in sorted(params.items())
    }
    query = urlencode(filtered)
    params["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return params


def _pack(operation: int, body: bytes, proto_ver: int = PROTOCOL_VERSION_HEARTBEAT) -> bytes:
    total = HEADER_LEN + len(body)
    return struct.pack(">IHHII", total, HEADER_LEN, proto_ver, operation, 1) + body


def _unpack_header(data: bytes):
    return struct.unpack(">IHHII", data[:HEADER_LEN])


def _decompress(data: bytes, proto_ver: int) -> bytes:
    if proto_ver == PROTOCOL_VERSION_ZLIB:
        return zlib.decompress(data)
    if proto_ver == PROTOCOL_VERSION_BROTLI:
        try:
            import brotli
            return brotli.decompress(data)
        except ImportError:
            if _module_logger:
                _module_logger("brotli 库未安装，无法解压 brotli 数据包", "warning")
            return b""
    return data


def _split_packets(data: bytes) -> List[bytes]:
    packets: List[bytes] = []
    offset = 0
    while offset < len(data):
        if len(data) - offset < HEADER_LEN:
            break
        total_len = struct.unpack(">I", data[offset:offset + 4])[0]
        if total_len < HEADER_LEN or offset + total_len > len(data):
            break
        packets.append(data[offset:offset + total_len])
        offset += total_len
    return packets


class _LiveDanmakuClient:
    def __init__(
        self,
        room_id: int,
        credential: Optional[Credential],
        logger,
        callbacks: Optional[Dict[str, Callable[..., None]]] = None,
        danmaku_max_length: int = 20,
    ) -> None:
        self.room_id = room_id
        self.real_room_id = room_id
        self.credential = credential
        self.logger = logger
        self.callbacks = callbacks or {}
        self.running = False
        self._stop_event = asyncio.Event()
        self._ws = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._buvid3_temp = ""
        self._danmaku_max_length = max(1, min(100, int(danmaku_max_length or 20)))
        self._wbi_mixin_key = ""
        self._wbi_key_ts = 0.0
        self._wbi_key_ttl = 43200.0

        global _module_logger
        if logger:
            _module_logger = lambda msg, level="info": getattr(logger, level, logger.info)(msg)

    def _log(self, msg: str, level: str = "info") -> None:
        if self.logger:
            getattr(self.logger, level, self.logger.info)(msg)

    def _emit(self, event: str, *args, **kwargs) -> None:
        cb = self.callbacks.get(event)
        if not cb:
            return
        try:
            cb(*args, **kwargs)
        except Exception as exc:
            self._log(f"回调 {event} 异常: {exc}", "warning")

    async def _get_wbi_mixin_key(self, cookies: Dict[str, str]) -> str:
        now = time.time()
        if self._wbi_mixin_key and (now - self._wbi_key_ts) < self._wbi_key_ttl:
            return self._wbi_mixin_key
        try:
            import aiohttp
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.bilibili.com/",
            }
            async with aiohttp.ClientSession(cookies=cookies) as session:
                async with session.get(
                    "https://api.bilibili.com/x/web-interface/nav",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as resp:
                    data = await resp.json()
                    wbi_img = data.get("data", {}).get("wbi_img", {})
                    img_url = wbi_img.get("img_url", "")
                    sub_url = wbi_img.get("sub_url", "")
                    img_key = img_url.rsplit("/", 1)[-1].split(".")[0] if img_url else ""
                    sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0] if sub_url else ""
                    if img_key and sub_key:
                        mixin_key = _get_mixin_key(img_key, sub_key)
                        if mixin_key:
                            self._wbi_mixin_key = mixin_key
                            self._wbi_key_ts = now
                            return mixin_key
        except Exception as exc:
            self._log(f"获取 WBI key 失败: {exc}", "warning")
        return ""

    async def _get_real_room_id(self, room_id: int) -> int:
        try:
            import aiohttp
            url = f"https://api.live.bilibili.com/xlive/web-room/v1/index/getInfoByRoom?room_id={room_id}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    data = await resp.json()
                    if data.get("code") == 0:
                        return int(data["data"]["room_info"]["room_id"])
        except Exception as exc:
            self._log(f"获取真实房间号失败: {exc}", "warning")
        return room_id

    async def _fetch_buvid3(self) -> str:
        try:
            import aiohttp
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://www.bilibili.com/",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=8),
                    allow_redirects=True,
                ) as resp:
                    buvid3 = resp.cookies.get("buvid3")
                    if buvid3:
                        return buvid3.value if hasattr(buvid3, "value") else str(buvid3)
                    for raw in resp.headers.getall("Set-Cookie", []):
                        if "buvid3=" not in raw:
                            continue
                        for part in raw.split(";"):
                            part = part.strip()
                            if part.startswith("buvid3="):
                                return part[len("buvid3="):]
        except Exception as exc:
            self._log(f"获取临时 buvid3 失败: {exc}", "warning")
        return ""

    async def _get_danmaku_server_info(self, real_room_id: int) -> tuple[str, str]:
        try:
            import aiohttp

            buvid3 = ""
            if self.credential:
                buvid3 = getattr(self.credential, "buvid3", "") or ""
            if not buvid3:
                buvid3 = await self._fetch_buvid3()
                if buvid3 and self.credential:
                    try:
                        self.credential.buvid3 = buvid3
                    except Exception:
                        pass
                self._buvid3_temp = buvid3

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": f"https://live.bilibili.com/{real_room_id}",
            }
            cookies: Dict[str, str] = {"buvid3": buvid3} if buvid3 else {}
            if self.credential:
                cookies.update({
                    "SESSDATA": getattr(self.credential, "sessdata", "") or "",
                    "bili_jct": getattr(self.credential, "bili_jct", "") or "",
                    "DedeUserID": getattr(self.credential, "dedeuserid", "") or "",
                })
                cookies = {k: v for k, v in cookies.items() if v}

            params = {"id": real_room_id, "type": 0}
            mixin_key = await self._get_wbi_mixin_key(cookies)
            if mixin_key:
                params = _wbi_sign(params, mixin_key)

            async with aiohttp.ClientSession(cookies=cookies) as session:
                async with session.get(
                    "https://api.live.bilibili.com/xlive/web-room/v1/index/getDanmuInfo",
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as resp:
                    data = await resp.json()
                    if data.get("code") == 0:
                        token = data["data"].get("token", "")
                        hosts = data["data"].get("host_list", [])
                        if hosts:
                            host = hosts[0]
                            return f"wss://{host['host']}:{host['wss_port']}/sub", token
        except Exception as exc:
            self._log(f"获取弹幕服务器信息失败: {exc}", "warning")
        return WS_URL, ""

    def _build_auth_body(self, real_room_id: int, token: str) -> bytes:
        uid = 0
        buvid3 = ""
        if self.credential:
            try:
                uid = int(getattr(self.credential, "dedeuserid", 0) or 0)
            except Exception:
                uid = 0
            buvid3 = getattr(self.credential, "buvid3", "") or ""
        if not buvid3:
            buvid3 = self._buvid3_temp
        body = {
            "uid": uid,
            "roomid": real_room_id,
            "protover": 2,
            "platform": "web",
            "type": 2,
            "key": token,
        }
        if buvid3:
            body["buvid"] = buvid3
        return json.dumps(body, separators=(",", ":")).encode("utf-8")

    async def _heartbeat_loop(self) -> None:
        try:
            while self.running and self._ws:
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=30)
                    break
                except asyncio.TimeoutError:
                    pass
                if self.running and self._ws:
                    try:
                        await self._ws.send(_pack(OPERATION_HEARTBEAT, b"[object Object]"))
                    except Exception:
                        break
        except asyncio.CancelledError:
            pass

    def _dispatch_message(self, cmd: str, data: dict) -> None:
        try:
            if cmd == "DANMU_MSG":
                info = data.get("info", [])
                if not isinstance(info, list) or len(info) < 2:
                    return
                content = str(info[1]) if info[1] is not None else ""
                user_info = info[2] if len(info) > 2 else []
                if isinstance(user_info, list):
                    user_id = user_info[0] if len(user_info) > 0 else 0
                    user_name = str(user_info[1]) if len(user_info) > 1 else "未知"
                else:
                    user_id, user_name = 0, "未知"
                user_level = 0
                if len(info) > 4 and isinstance(info[4], list) and len(info[4]) > 0:
                    try:
                        user_level = int(info[4][0])
                    except (TypeError, ValueError):
                        user_level = 0
                try:
                    ts = info[0][4] / 1000 if isinstance(info[0], list) and len(info[0]) > 4 else None
                    time_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else datetime.now().strftime("%H:%M:%S")
                except Exception:
                    time_str = datetime.now().strftime("%H:%M:%S")
                medal_text = ""
                if len(info) > 3 and isinstance(info[3], list) and len(info[3]) >= 2:
                    try:
                        medal_level = int(info[3][0])
                        medal_name = str(info[3][1])
                        medal_text = f"[{medal_name}{medal_level}]"
                    except Exception:
                        pass
                self._emit("on_danmaku", {
                    "time": time_str,
                    "content": content,
                    "user_id": user_id,
                    "user_name": user_name,
                    "user_level": user_level,
                    "medal_text": medal_text,
                    "medal_level": 0,
                    "medal_name": "",
                })
            elif cmd == "SEND_GIFT":
                inner = data.get("data", {})
                self._emit("on_gift", {
                    "user_name": inner.get("uname", "未知"),
                    "user_id": inner.get("uid", 0),
                    "gift_name": inner.get("giftName", "未知礼物"),
                    "num": inner.get("num", 1),
                    "coin_type": inner.get("coin_type", "silver"),
                    "total_coin": inner.get("total_coin", 0),
                    "price": inner.get("price", 0),
                })
            elif cmd == "SUPER_CHAT_MESSAGE":
                inner = data.get("data", {})
                user_info = inner.get("user_info", {})
                self._emit("on_sc", {
                    "user_name": user_info.get("uname", "未知"),
                    "user_id": inner.get("uid", 0),
                    "message": inner.get("message", ""),
                    "price": inner.get("price", 0),
                    "start_time": inner.get("start_time", 0),
                })
            elif cmd == "LIVE":
                self._emit("on_live")
            elif cmd == "PREPARING":
                self._emit("on_preparing")
        except Exception as exc:
            self._log(f"分发消息 {cmd} 异常: {exc}", "debug")

    def _process_packet(self, raw: bytes) -> None:
        if len(raw) < HEADER_LEN:
            return
        total_len, header_len, proto_ver, operation, _seq = _unpack_header(raw)
        body = raw[header_len:total_len]
        if operation == OPERATION_HEARTBEAT_REPLY:
            return
        if operation == OPERATION_AUTH_REPLY:
            try:
                result = json.loads(body.decode("utf-8"))
                if result.get("code") != 0:
                    self.running = False
                    self._stop_event.set()
                    self._log(f"认证失败: {result}", "warning")
            except Exception as exc:
                self._log(f"解析认证回包异常: {exc}", "debug")
            return
        if operation != OPERATION_SEND_MSG:
            return
        if proto_ver in (PROTOCOL_VERSION_ZLIB, PROTOCOL_VERSION_BROTLI):
            try:
                decompressed = _decompress(body, proto_ver)
                for pkt in _split_packets(decompressed):
                    self._process_packet(pkt)
            except Exception as exc:
                self._log(f"解压失败: {exc}", "warning")
            return
        try:
            msg = json.loads(body.decode("utf-8"))
            cmd = str(msg.get("cmd", "")).split(":")[0]
            self._dispatch_message(cmd, msg)
        except Exception as exc:
            self._log(f"解析消息失败: {exc}", "warning")

    async def _connect_once(self) -> None:
        import inspect
        import websockets

        if self._stop_event.is_set():
            return
        real_room_id = await self._get_real_room_id(self.room_id)
        if self._stop_event.is_set():
            return
        self.real_room_id = real_room_id
        ws_url, token = await self._get_danmaku_server_info(real_room_id)
        if self._stop_event.is_set():
            return
        auth_body = self._build_auth_body(real_room_id, token)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://live.bilibili.com",
        }
        sig = inspect.signature(websockets.connect)
        ws_kwargs = {"additional_headers": headers} if "additional_headers" in sig.parameters else {"extra_headers": headers}
        try:
            async with websockets.connect(ws_url, ping_interval=None, **ws_kwargs) as ws:
                self._ws = ws
                await ws.send(_pack(OPERATION_AUTH, auth_body))
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                async for message in ws:
                    if self._stop_event.is_set():
                        break
                    if isinstance(message, bytes):
                        self._process_packet(message)
        finally:
            if self._heartbeat_task and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
            self._ws = None

    async def start(self) -> None:
        self._stop_event.clear()
        self.running = True
        retry_count = 0
        while True:
            if self._stop_event.is_set():
                break
            try:
                await self._connect_once()
            except Exception as exc:
                self._log(f"连接过程异常: {exc}", "error")
                self._emit("on_error", exc)
            if self._stop_event.is_set():
                break
            retry_count += 1
            if retry_count > 10:
                break
            wait = min(5 * retry_count, 60)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=wait)
                break
            except asyncio.TimeoutError:
                pass
        self.running = False

    async def send_danmaku(
        self,
        message: str,
        room_id: int,
        credential: Optional[Credential] = None,
        danmaku_max_length: int = 20,
    ) -> Dict[str, Any]:
        if not credential:
            return {"success": False, "message": "未登录，无法发送弹幕"}
        bili_jct = getattr(credential, "bili_jct", "")
        sessdata = getattr(credential, "sessdata", "")
        dedeuserid = getattr(credential, "dedeuserid", "")
        if not bili_jct:
            return {"success": False, "message": "缺少 bili_jct，无法发送弹幕"}
        message = str(message).strip()
        if not message:
            return {"success": False, "message": "弹幕内容不能为空"}
        max_len = danmaku_max_length or self._danmaku_max_length or 20
        if len(message) > max_len:
            message = message[:max_len]
        try:
            import aiohttp
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": f"https://live.bilibili.com/{room_id}",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            cookies = {
                "SESSDATA": sessdata,
                "bili_jct": bili_jct,
                "DedeUserID": dedeuserid,
            }
            cookies = {k: v for k, v in cookies.items() if v}
            payload = {
                "bubble": "0",
                "msg": message,
                "color": "16777215",
                "mode": "1",
                "fontsize": "25",
                "rnd": int(time.time() * 1000000) + random.randint(0, 999),
                "roomid": room_id,
                "csrf": bili_jct,
                "csrf_token": bili_jct,
            }
            async with aiohttp.ClientSession(cookies=cookies) as session:
                async with session.post(
                    "https://api.live.bilibili.com/msg/send",
                    data=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as resp:
                    data = await resp.json()
                    if data.get("code") == 0:
                        return {"success": True, "message": f"弹幕发送成功: {message}"}
                    msg = data.get("message", "未知错误")
                    return {"success": False, "message": f"发送失败: {msg} (code={data.get('code', -1)})"}
        except Exception as exc:
            self._log(f"弹幕发送异常: {exc}", "error")
            return {"success": False, "message": f"发送异常: {exc}"}

    async def stop(self) -> None:
        self.running = False
        self._stop_event.set()
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None

    def is_running(self) -> bool:
        return self.running


class BilibiliNativeService:
    VIDEO_ZONES = {
        "科技": {
            188: "科技资讯", 122: "野生技术协会", 95: "数码",
            208: "科技", 209: "手工",
        },
        "知识": {
            201: "科学", 124: "社科·法律·心理", 207: "财经商业",
            228: "人文历史", 36: "科技(知识)",
        },
        "生活": {
            21: "日常", 160: "生活记录", 230: "其他",
            231: "美食", 234: "健身", 161: "搞笑",
        },
        "游戏": {
            17: "单机游戏", 171: "电子竞技", 172: "手机游戏",
            65: "网络游戏",
        },
        "影视": {
            183: "影视杂谈", 138: "搞笑", 182: "影视剪辑",
        },
        "动画": {
            32: "完结动画", 33: "连载动画", 51: "MAD·AMV",
        },
        "音乐": {
            28: "原创音乐", 31: "翻唱", 59: "演奏",
        },
    }

    def __init__(self, plugin_dir: Path, logger) -> None:
        self.plugin_dir = plugin_dir
        self.logger = logger
        self.credential_file = plugin_dir / "bili_credential.json"
        self.qr_file = plugin_dir / "qrcode_login.png"
        self._login_session: Optional[QrCodeLogin] = None
        self.live_room_id: int = 0
        self.live_danmaku_max_length: int = 20
        self.live_listener: Optional[_LiveDanmakuClient] = None
        self.live_listen_task = None
        self.live_connecting = False
        self.live_danmaku_queue: Deque[Dict[str, Any]] = deque(maxlen=200)
        self.live_sc_queue: Deque[Dict[str, Any]] = deque(maxlen=50)
        self.live_gift_queue: Deque[Dict[str, Any]] = deque(maxlen=50)
        self.live_event_queue: Deque[Dict[str, Any]] = deque(maxlen=50)
        self.live_total_received = 0

    def load_credential(self) -> Optional[Credential]:
        if not self.credential_file.exists():
            return None
        with self.credential_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return Credential(
            sessdata=data.get("sessdata", ""),
            bili_jct=data.get("bili_jct", ""),
            buvid3=data.get("buvid3") or "",
            dedeuserid=data.get("dedeuserid", ""),
        )

    def save_credential(self, cred: Credential) -> None:
        payload = {
            "sessdata": cred.sessdata,
            "bili_jct": cred.bili_jct,
            "buvid3": cred.buvid3,
            "dedeuserid": cred.dedeuserid,
        }
        with self.credential_file.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

    def clear_qr_artifacts(self) -> None:
        self._login_session = None
        try:
            if self.qr_file.exists():
                self.qr_file.unlink()
        except Exception:
            if self.logger:
                self.logger.debug("Failed to remove QR file", exc_info=True)

    def configure_live(self, *, room_id: int = 0, danmaku_max_length: int = 20) -> None:
        self.live_room_id = max(0, int(room_id or 0))
        self.live_danmaku_max_length = max(1, min(100, int(danmaku_max_length or 20)))

    def _build_live_credential(self) -> Optional[Credential]:
        return self.load_credential()

    def _append_live_event(self, queue: Deque[Dict[str, Any]], payload: Dict[str, Any]) -> None:
        queue.append(payload)
        self.live_total_received += 1

    def _on_live_danmaku(self, data: Dict[str, Any]) -> None:
        self._append_live_event(self.live_danmaku_queue, data)

    def _on_live_gift(self, data: Dict[str, Any]) -> None:
        self._append_live_event(self.live_gift_queue, data)

    def _on_live_sc(self, data: Dict[str, Any]) -> None:
        self._append_live_event(self.live_sc_queue, data)

    def _on_live_status(self, event_type: str, message: str) -> None:
        self.live_event_queue.append({"type": event_type, "message": message})

    def _on_live_error(self, error: Exception) -> None:
        self.live_event_queue.append({"type": "error", "message": str(error)})

    async def _run_live_listener(self, listener: _LiveDanmakuClient) -> None:
        try:
            await listener.start()
        finally:
            if self.live_listener is listener:
                self.live_connecting = False

    async def set_live_room_id(self, room_id: int) -> Dict[str, Any]:
        if room_id <= 0:
            raise RuntimeError("room_id 必须是正整数")
        old_room_id = self.live_room_id
        self.live_room_id = int(room_id)
        if self.live_listener and (self.live_listener.is_running() or self.live_connecting):
            await self.start_live_listener(room_id=self.live_room_id, restart=True)
        return {
            "room_id": self.live_room_id,
            "old_room_id": old_room_id,
            "restarting": bool(old_room_id and old_room_id != self.live_room_id),
        }

    async def start_live_listener(self, room_id: int = 0, restart: bool = False) -> Dict[str, Any]:
        if room_id > 0:
            self.live_room_id = int(room_id)
        if self.live_room_id <= 0:
            raise RuntimeError("未设置直播间ID")
        if restart:
            await self.stop_live_listener()
        elif self.live_listener and (self.live_listener.is_running() or self.live_connecting):
            return {
                "room_id": self.live_room_id,
                "connecting": self.live_connecting,
                "listening": self.live_listener.is_running(),
                "message": f"已在监听直播间 {self.live_room_id}",
            }

        credential = self._build_live_credential()
        listener = _LiveDanmakuClient(
            room_id=self.live_room_id,
            credential=credential,
            logger=self.logger,
            callbacks={
                "on_danmaku": self._on_live_danmaku,
                "on_gift": self._on_live_gift,
                "on_sc": self._on_live_sc,
                "on_live": lambda: self._on_live_status("live", f"直播间 {self.live_room_id} 开播了"),
                "on_preparing": lambda: self._on_live_status("preparing", f"直播间 {self.live_room_id} 已下播"),
                "on_error": self._on_live_error,
            },
            danmaku_max_length=self.live_danmaku_max_length,
        )
        self.live_listener = listener
        self.live_connecting = True
        self.live_listen_task = __import__("asyncio").create_task(self._run_live_listener(listener))
        return {
            "room_id": self.live_room_id,
            "connecting": True,
            "listening": False,
            "message": f"正在连接直播间 {self.live_room_id}",
        }

    async def stop_live_listener(self) -> Dict[str, Any]:
        listener = self.live_listener
        task = self.live_listen_task
        self.live_listener = None
        self.live_listen_task = None
        self.live_connecting = False
        if listener is not None:
            await listener.stop()
        if task is not None:
            try:
                await task
            except Exception:
                pass
        return {"room_id": self.live_room_id, "stopped": True}

    async def get_live_status(self) -> Dict[str, Any]:
        listener = self.live_listener
        listening = bool(listener and listener.is_running())
        real_room_id = getattr(listener, "real_room_id", self.live_room_id) if listener else self.live_room_id
        return {
            "room_id": self.live_room_id,
            "real_room_id": real_room_id,
            "connecting": self.live_connecting,
            "listening": listening,
            "logged_in": self.load_credential() is not None,
            "danmaku_max_length": self.live_danmaku_max_length,
            "queue_size": len(self.live_danmaku_queue),
            "sc_queue_size": len(self.live_sc_queue),
            "gift_queue_size": len(self.live_gift_queue),
            "received": self.live_total_received,
        }

    async def drain_live_events(self, max_count: int = 10, include_gifts: bool = True) -> Dict[str, Any]:
        max_count = max(1, min(30, int(max_count or 10)))
        danmaku = []
        while self.live_danmaku_queue and len(danmaku) < max_count:
            danmaku.append(self.live_danmaku_queue.popleft())
        superchat = []
        while self.live_sc_queue:
            superchat.append(self.live_sc_queue.popleft())
        gifts = []
        if include_gifts:
            while self.live_gift_queue and len(gifts) < 5:
                gifts.append(self.live_gift_queue.popleft())
        events = []
        while self.live_event_queue:
            events.append(self.live_event_queue.popleft())
        status = await self.get_live_status()
        status.update({
            "danmaku": danmaku,
            "superchat": superchat,
            "gifts": gifts,
            "events": events,
            "danmaku_count": len(danmaku),
            "sc_count": len(superchat),
            "gift_count": len(gifts),
            "event_count": len(events),
        })
        return status

    async def send_live_danmaku(self, message: str) -> Dict[str, Any]:
        listener = self.live_listener
        if not listener:
            raise RuntimeError("当前未连接直播间")
        credential = self._build_live_credential()
        if credential is None:
            raise RuntimeError("未登录B站！请先调用 bili_login 获取登录二维码。")
        room_id = getattr(listener, "real_room_id", 0) or self.live_room_id
        return await listener.send_danmaku(
            message=message,
            room_id=room_id,
            credential=credential,
            danmaku_max_length=self.live_danmaku_max_length,
        )

    def open_qr_in_browser(self) -> None:
        if not self.qr_file.exists():
            raise RuntimeError(f"二维码文件不存在: {self.qr_file}")
        startfile = getattr(os, "startfile", None)
        if callable(startfile):
            startfile(str(self.qr_file))
            return
        opened = webbrowser.open(self.qr_file.resolve().as_uri())
        if not opened:
            raise RuntimeError("默认浏览器未接受二维码文件打开请求")

    async def get_valid_credential(self) -> Credential:
        cred = self.load_credential()
        if not cred:
            raise RuntimeError("未登录B站！请先调用 bili_login 获取登录二维码。")
        return cred

    async def login(self) -> Dict[str, Any]:
        cred = self.load_credential()
        if cred:
            try:
                uid = int(cred.dedeuserid)
                my_info = await user.User(uid=uid, credential=cred).get_user_info()
                return {
                    "status": "already_logged_in",
                    "message": "已登录B站，无需重复登录",
                    "uid": cred.dedeuserid,
                    "username": my_info.get("name", ""),
                }
            except Exception:
                pass

        self._login_session = QrCodeLogin()
        await self._login_session.generate_qrcode()
        pic = self._login_session.get_qrcode_picture()
        png_bytes = pic.content
        img_base64 = base64.b64encode(png_bytes).decode("utf-8")
        with self.qr_file.open("wb") as f:
            f.write(png_bytes)
        terminal_qr = self._login_session.get_qrcode_terminal()
        qr_url = getattr(self._login_session, "_QrCodeLogin__qr_link", "")
        return {
            "status": "qrcode_ready",
            "message": "请用B站App扫描二维码登录（180秒内有效）",
            "qrcode_image": f"data:image/png;base64,{img_base64}",
            "qrcode_file": str(self.qr_file),
            "qrcode_terminal": terminal_qr,
            "qrcode_url": qr_url,
            "next_step": "用户扫码后，请调用 bili_login_check 检查登录状态",
        }

    async def login_check(self) -> Dict[str, Any]:
        if not self._login_session:
            cred = self.load_credential()
            if cred:
                return {
                    "status": "already_logged_in",
                    "message": "已登录B站",
                }
            return {
                "status": "no_session",
                "message": "没有进行中的登录，请先调用 bili_login 生成二维码",
            }

        state = await self._login_session.check_state()
        if state == QrCodeLoginEvents.SCAN:
            return {
                "status": "scanning",
                "message": "已扫码，等待用户在手机上确认...",
                "next_step": "请等待3秒后再次调用 bili_login_check",
            }
        if state == QrCodeLoginEvents.CONF:
            return {
                "status": "confirming",
                "message": "用户已确认，正在处理...",
                "next_step": "请等待2秒后再次调用 bili_login_check",
            }
        if state == QrCodeLoginEvents.TIMEOUT:
            self.clear_qr_artifacts()
            return {
                "status": "timeout",
                "message": "二维码已过期，请重新调用 bili_login 生成新二维码",
            }
        if state == QrCodeLoginEvents.DONE:
            cred = self._login_session.get_credential()
            self.save_credential(cred)
            self.clear_qr_artifacts()
            return {
                "status": "done",
                "message": "登录成功！凭证已保存，现在可以使用所有B站功能了",
            }
        return {
            "status": "unknown",
            "message": f"未知状态: {state}",
        }

    async def check_credential(self) -> Dict[str, Any]:
        cred = self.load_credential()
        if not cred:
            return {
                "logged_in": False,
                "message": "未登录，请调用 bili_login 进行扫码登录",
            }
        try:
            uid = int(cred.dedeuserid)
            my_info = await user.User(uid=uid, credential=cred).get_user_info()
            return {
                "logged_in": True,
                "uid": cred.dedeuserid,
                "username": my_info.get("name", ""),
                "message": "凭证有效",
            }
        except Exception as e:
            return {
                "logged_in": False,
                "message": f"凭证可能已过期: {str(e)}，请重新调用 bili_login 登录",
            }

    async def _resolve_video_by_keyword(self, keyword: str) -> Dict[str, Any]:
        if not keyword or not keyword.strip():
            raise RuntimeError("keyword 不能为空")
        search_result = await self.search_videos(keyword=keyword.strip(), num=1)
        videos = search_result.get("videos") or []
        if not videos:
            raise RuntimeError(f"未找到关键词对应的视频: {keyword}")
        first = videos[0] if isinstance(videos[0], dict) else {}
        bvid = first.get("bvid") if isinstance(first.get("bvid"), str) else ""
        if not bvid:
            raise RuntimeError(f"搜索结果缺少有效 bvid: {keyword}")
        return {
            "keyword": keyword.strip(),
            "matched_bvid": bvid,
            "matched_title": first.get("title") if isinstance(first.get("title"), str) else "",
        }

    def _attach_keyword_match(self, payload: Dict[str, Any], matched: Dict[str, Any]) -> Dict[str, Any]:
        payload["keyword"] = matched["keyword"]
        payload["matched_bvid"] = matched["matched_bvid"]
        if matched.get("matched_title"):
            payload["matched_title"] = matched["matched_title"]
        return payload

    async def _get_video_and_info(self, *, bvid: str) -> tuple[video.Video, Dict[str, Any], Credential]:
        cred = await self.get_valid_credential()
        v = video.Video(bvid=bvid, credential=cred)
        info = await v.get_info()
        return v, info, cred

    async def _get_video_cid(self, *, bvid: str) -> tuple[video.Video, Dict[str, Any], int]:
        v, info, _ = await self._get_video_and_info(bvid=bvid)
        cid = info.get("cid", 0)
        if not cid and info.get("pages"):
            cid = info["pages"][0].get("cid", 0)
        if not cid:
            raise RuntimeError("无法获取cid")
        return v, info, cid

    async def _fetch_subtitle_payload(self, *, bvid: str) -> Dict[str, Any]:
        import aiohttp

        v, info, cid = await self._get_video_cid(bvid=bvid)
        subtitle_list = await v.get_subtitle(cid=cid)
        subtitles = subtitle_list.get("subtitles", [])
        if not subtitles:
            return {
                "bvid": bvid,
                "title": info.get("title", ""),
                "message": "该视频没有字幕",
                "segments": 0,
                "text": "",
            }
        target = None
        for subtitle in subtitles:
            if subtitle.get("lan") in ["ai-zh", "zh-CN", "zh"]:
                target = subtitle
                break
        if not target:
            target = subtitles[0]
        sub_url = target.get("subtitle_url", "")
        if sub_url.startswith("//"):
            sub_url = "https:" + sub_url
        async with aiohttp.ClientSession() as client:
            async with client.get(sub_url) as resp:
                sub_data = await resp.json()
        texts = [item.get("content", "") for item in sub_data.get("body", [])]
        return {
            "bvid": bvid,
            "title": info.get("title", ""),
            "language": target.get("lan_doc", ""),
            "segments": len(texts),
            "text": "\n".join(texts),
        }

    async def subtitle(self, *, bvid: str) -> Dict[str, Any]:
        return await self._fetch_subtitle_payload(bvid=bvid)

    async def subtitle_by_keyword(self, keyword: str) -> Dict[str, Any]:
        matched = await self._resolve_video_by_keyword(keyword)
        payload = await self.subtitle(bvid=matched["matched_bvid"])
        return self._attach_keyword_match(payload, matched)

    async def danmaku(self, *, bvid: str, num: int = 100) -> Dict[str, Any]:
        v, _, _ = await self._get_video_and_info(bvid=bvid)
        danmakus = await v.get_danmakus(page_index=0)
        result: List[Dict[str, Any]] = []
        for item in danmakus[:num]:
            result.append({
                "text": item.text,
                "time": item.dm_time,
            })
        return {"bvid": bvid, "count": len(result), "danmakus": result}

    async def danmaku_by_keyword(self, keyword: str, num: int = 100) -> Dict[str, Any]:
        matched = await self._resolve_video_by_keyword(keyword)
        payload = await self.danmaku(bvid=matched["matched_bvid"], num=num)
        return self._attach_keyword_match(payload, matched)

    async def search_videos(self, keyword: str, num: int = 10, order: str = "totalrank") -> Dict[str, Any]:
        order_map = {
            "totalrank": search.OrderVideo.TOTALRANK,
            "click": search.OrderVideo.CLICK,
            "pubdate": search.OrderVideo.PUBDATE,
            "dm": search.OrderVideo.DM,
        }
        order_enum = order_map.get(order, search.OrderVideo.TOTALRANK)
        result = await search.search_by_type(
            keyword=keyword,
            search_type=search.SearchObjectType.VIDEO,
            page=1,
            order_type=order_enum,
        )
        videos: List[Dict[str, Any]] = []
        for item in result.get("result", [])[:num]:
            title = item.get("title", "").replace('<em class="keyword">', "").replace("</em>", "")
            videos.append({
                "bvid": item.get("bvid", ""),
                "aid": item.get("aid", 0),
                "title": title,
                "author": item.get("author", ""),
                "play": item.get("play", 0),
                "review": item.get("review", 0),
                "danmaku": item.get("video_review", 0),
                "duration": item.get("duration", ""),
                "description": item.get("description", "")[:200],
            })
        return {"keyword": keyword, "count": len(videos), "videos": videos}

    async def hot_videos(self, pn: int = 1, ps: int = 20) -> Dict[str, Any]:
        result = await hot.get_hot_videos(pn=pn, ps=min(ps, 50))
        videos: List[Dict[str, Any]] = []
        for item in result.get("list", []):
            stat = item.get("stat", {})
            videos.append({
                "bvid": item.get("bvid", ""),
                "title": item.get("title", ""),
                "author": item.get("owner", {}).get("name", ""),
                "play": stat.get("view", 0),
                "like": stat.get("like", 0),
                "danmaku": stat.get("danmaku", 0),
                "reply": stat.get("reply", 0),
                "desc": (item.get("desc", "") or "")[:100],
                "duration": item.get("duration", 0),
                "tname": item.get("tname", ""),
            })
        return {"page": pn, "count": len(videos), "videos": videos}

    async def video_info(self, *, bvid: Optional[str] = None, aid: Optional[int] = None) -> Dict[str, Any]:
        cred = await self.get_valid_credential()
        if bvid:
            v = video.Video(bvid=bvid, credential=cred)
        elif aid is not None:
            v = video.Video(aid=aid, credential=cred)
        else:
            raise RuntimeError("bvid or aid is required")
        info = await v.get_info()
        stat = info.get("stat", {})
        return {
            "bvid": info.get("bvid"),
            "aid": info.get("aid"),
            "title": info.get("title"),
            "description": info.get("desc"),
            "author": info.get("owner", {}).get("name"),
            "duration": info.get("duration"),
            "pages": len(info.get("pages", [])),
            "tags": [t.get("tag_name") for t in info.get("tag", []) if t.get("tag_name")],
            "stat": {
                "view": stat.get("view", 0),
                "danmaku": stat.get("danmaku", 0),
                "reply": stat.get("reply", 0),
                "favorite": stat.get("favorite", 0),
                "coin": stat.get("coin", 0),
                "like": stat.get("like", 0),
                "share": stat.get("share", 0),
            },
        }

    async def comments_by_keyword(self, keyword: str, num: int = 30) -> Dict[str, Any]:
        matched = await self._resolve_video_by_keyword(keyword)
        comments_result = await self.comments(bvid=matched["matched_bvid"], num=num)
        return self._attach_keyword_match(comments_result, matched)

    async def comments(self, *, bvid: str, num: int = 30) -> Dict[str, Any]:
        cred = await self.get_valid_credential()
        v = video.Video(bvid=bvid, credential=cred)
        info = await v.get_info()
        aid = info["aid"]
        comments: List[Dict[str, Any]] = []
        page = 1
        while len(comments) < num:
            try:
                resp = await comment.get_comments(
                    oid=aid,
                    type_=comment.CommentResourceType.VIDEO,
                    page_index=page,
                    order=comment.OrderType.LIKE,
                    credential=cred,
                )
                replies = resp.get("replies") or []
                if not replies:
                    break
                for r in replies:
                    member = r.get("member", {})
                    content = r.get("content", {})
                    item: Dict[str, Any] = {
                        "rpid": r.get("rpid", 0),
                        "user": member.get("uname", ""),
                        "content": content.get("message", ""),
                        "like": r.get("like", 0),
                        "reply_count": r.get("rcount", 0),
                        "time": r.get("ctime", 0),
                    }
                    sub_replies = []
                    for sub in (r.get("replies") or [])[:2]:
                        sub_replies.append({
                            "user": sub.get("member", {}).get("uname", ""),
                            "content": sub.get("content", {}).get("message", ""),
                            "like": sub.get("like", 0),
                        })
                    if sub_replies:
                        item["top_replies"] = sub_replies
                    comments.append(item)
                    if len(comments) >= num:
                        break
                page += 1
            except Exception:
                break
        return {"bvid": bvid, "count": len(comments[:num]), "comments": comments[:num]}

    async def video_zones(self) -> Dict[str, Dict[int, str]]:
        return self.VIDEO_ZONES

    async def hot_buzzwords(self, page_num: int = 1, page_size: int = 20) -> Dict[str, Any]:
        return await hot.get_hot_buzzwords(page_num=page_num, page_size=page_size)

    async def weekly_hot(self, week: int = 0) -> Dict[str, Any]:
        if week <= 0:
            return await hot.get_weekly_hot_videos_list()
        return await hot.get_weekly_hot_videos(week=week)

    async def rank_videos(self, category: str = "all", day: int = 3) -> Dict[str, Any]:
        type_map = {
            "all": rank.RankType.All,
            "original": rank.RankType.Original,
            "rookie": rank.RankType.Rookie,
            "douga": rank.RankType.Douga,
            "music": rank.RankType.Music,
            "dance": rank.RankType.Dance,
            "game": rank.RankType.Game,
            "knowledge": rank.RankType.Knowledge,
            "technology": rank.RankType.Technology,
            "sports": rank.RankType.Sports,
            "car": rank.RankType.Car,
            "life": rank.RankType.Life,
            "food": rank.RankType.Food,
            "animal": rank.RankType.Animal,
            "fashion": rank.RankType.Fashion,
            "ent": rank.RankType.Ent,
            "cinephile": rank.RankType.Cinephile,
        }
        day_map = {3: rank.RankDayType.THREE_DAY, 7: rank.RankDayType.WEEK}
        rank_type = type_map.get(category.lower(), rank.RankType.All)
        rank_day = day_map.get(day, rank.RankDayType.THREE_DAY)
        result = await rank.get_rank(type_=rank_type, day=rank_day)
        videos: List[Dict[str, Any]] = []
        for item in result.get("list", []):
            stat = item.get("stat", {})
            videos.append({
                "bvid": item.get("bvid", ""),
                "title": item.get("title", ""),
                "author": item.get("owner", {}).get("name", ""),
                "play": stat.get("view", 0),
                "like": stat.get("like", 0),
                "coin": stat.get("coin", 0),
                "score": item.get("score", 0),
                "tname": item.get("tname", ""),
            })
        return {"category": category, "day": day, "count": len(videos), "videos": videos}

    async def user_info(self, uid: int) -> Dict[str, Any]:
        cred = await self.get_valid_credential()
        target = user.User(uid=uid, credential=cred)
        info = await target.get_user_info()
        up_stat: Dict[str, Any] = {}
        relation: Dict[str, Any] = {}
        try:
            up_stat = await target.get_up_stat()
        except Exception:
            pass
        try:
            relation = await target.get_relation_info()
        except Exception:
            pass
        return {
            "uid": uid,
            "name": info.get("name", ""),
            "sign": info.get("sign", ""),
            "level": info.get("level", 0),
            "face": info.get("face", ""),
            "fans": relation.get("follower", info.get("follower", 0)),
            "following": relation.get("following", info.get("following", 0)),
            "likes": up_stat.get("likes", 0),
            "archive_view": up_stat.get("archive", {}).get("view", 0),
            "article_view": up_stat.get("article", {}).get("view", 0),
            "is_senior_member": info.get("is_senior_member", 0),
            "top_photo": info.get("top_photo", ""),
        }

    async def user_videos(self, uid: int, pn: int = 1, ps: int = 30, order: str = "pubdate", keyword: str = "") -> Dict[str, Any]:
        cred = await self.get_valid_credential()
        target = user.User(uid=uid, credential=cred)
        order_map = {
            "pubdate": user.VideoOrder.PUBDATE,
            "click": user.VideoOrder.VIEW,
            "stow": user.VideoOrder.FAVORITE,
        }
        order_enum = order_map.get(order, user.VideoOrder.PUBDATE)
        result = await target.get_videos(pn=pn, ps=ps, order=order_enum, keyword=keyword)
        videos: List[Dict[str, Any]] = []
        for item in result.get("list", {}).get("vlist", []):
            videos.append({
                "bvid": item.get("bvid", ""),
                "title": item.get("title", ""),
                "play": item.get("play", 0),
                "comment": item.get("comment", 0),
                "created": item.get("created", 0),
                "length": item.get("length", ""),
                "description": (item.get("description", "") or "")[:100],
            })
        return {
            "uid": uid,
            "page": pn,
            "total": result.get("page", {}).get("count", 0),
            "count": len(videos),
            "videos": videos,
        }

    async def favorite_lists(self, uid: int = 0) -> Dict[str, Any]:
        cred = await self.get_valid_credential()
        target_uid = uid
        if target_uid == 0:
            try:
                target_uid = int(cred.dedeuserid)
            except Exception as exc:
                raise RuntimeError("无法从当前凭证解析 UID") from exc
        result = await favorite_list.get_video_favorite_list(uid=target_uid, credential=cred)
        fav_lists: List[Dict[str, Any]] = []
        for item in result.get("list", []) or []:
            fav_lists.append({
                "id": item.get("id", 0),
                "title": item.get("title", ""),
                "media_count": item.get("media_count", 0),
                "fav_state": item.get("fav_state", 0),
            })
        return {"uid": target_uid, "count": len(fav_lists), "lists": fav_lists}

    async def favorite_content(self, media_id: int, page: int = 1, keyword: str = "") -> Dict[str, Any]:
        cred = await self.get_valid_credential()
        result = await favorite_list.get_video_favorite_list_content(
            media_id=media_id,
            page=page,
            keyword=keyword if keyword else None,
            credential=cred,
        )
        medias: List[Dict[str, Any]] = []
        for item in result.get("medias", []) or []:
            medias.append({
                "bvid": item.get("bvid", ""),
                "title": item.get("title", ""),
                "play": item.get("cnt_info", {}).get("play", 0),
                "collect": item.get("cnt_info", {}).get("collect", 0),
                "author": item.get("upper", {}).get("name", ""),
                "duration": item.get("duration", 0),
                "fav_time": item.get("fav_time", 0),
            })
        return {
            "media_id": media_id,
            "page": page,
            "has_more": result.get("has_more", False),
            "count": len(medias),
            "medias": medias,
        }

    async def unread_messages(self) -> Dict[str, Any]:
        cred = await self.get_valid_credential()
        return await session.get_unread_messages(credential=cred)

    async def received_replies(self) -> Dict[str, Any]:
        cred = await self.get_valid_credential()
        return await session.get_replies(credential=cred)

    async def received_at_and_likes(self) -> Dict[str, Any]:
        cred = await self.get_valid_credential()
        result: Dict[str, Any] = {}
        try:
            result["at"] = await session.get_at(credential=cred)
        except Exception as e:
            result["at_error"] = str(e)
        try:
            result["likes"] = await session.get_likes(credential=cred)
        except Exception as e:
            result["likes_error"] = str(e)
        return result

    async def reply(self, *, bvid: str, text: str, rpid: int = 0, root: int = 0) -> Dict[str, Any]:
        if not text or not text.strip():
            raise RuntimeError("text 不能为空")
        _, info, cred = await self._get_video_and_info(bvid=bvid)
        aid = info["aid"]
        if rpid == 0:
            result = await comment.send_comment(
                text=text.strip(),
                oid=aid,
                type_=comment.CommentResourceType.VIDEO,
                credential=cred,
            )
        else:
            actual_root = root if root != 0 else rpid
            result = await comment.send_comment(
                text=text.strip(),
                oid=aid,
                type_=comment.CommentResourceType.VIDEO,
                root=actual_root,
                parent=rpid,
                credential=cred,
            )
        return {
            "success": True,
            "message": "评论发送成功",
            "data": result if isinstance(result, dict) else str(result),
        }

    async def crawl(self, keyword: str, max_videos: int = 5, comments_per_video: int = 20, get_subtitles: bool = True) -> Dict[str, Any]:
        search_result = await self.search_videos(keyword=keyword, num=max_videos, order="totalrank")
        results: List[Dict[str, Any]] = []
        for item in search_result.get("videos", [])[:max_videos]:
            bvid = item.get("bvid", "") if isinstance(item, dict) else ""
            if not bvid:
                continue
            comments_data = await self.comments(bvid=bvid, num=comments_per_video)
            subtitle_text = ""
            if get_subtitles:
                try:
                    subtitle_data = await self.subtitle(bvid=bvid)
                    subtitle_text = subtitle_data.get("text", "") if isinstance(subtitle_data, dict) else ""
                except Exception:
                    pass
            results.append({
                "video": {
                    "bvid": bvid,
                    "title": item.get("title", ""),
                    "author": item.get("author", ""),
                    "play": item.get("play", 0),
                    "review": item.get("review", 0),
                },
                "comments": comments_data.get("comments", []),
                "subtitle_text": subtitle_text,
            })
        return {
            "keyword": keyword,
            "video_count": len(results),
            "total_comments": sum(len(entry.get("comments", [])) for entry in results),
            "results": results,
        }

    async def send_dynamic(self, text: str, images: Optional[List[str]] = None, topic_id: int = 0, schedule_time: int = 0) -> Dict[str, Any]:
        if not text or not text.strip():
            raise RuntimeError("text 不能为空")
        cred = await self.get_valid_credential()
        dyn = dynamic.BuildDynamic.empty()
        dyn.add_plain_text(text.strip())
        if images:
            for img_path in images[:9]:
                if not img_path or not img_path.strip():
                    continue
                img_path = img_path.strip()
                if img_path.startswith(("http://", "https://")):
                    pic = await Picture.async_from_url(img_path)
                else:
                    if not os.path.isfile(img_path):
                        raise RuntimeError(f"图片文件不存在: {img_path}")
                    pic = Picture.from_file(img_path)
                dyn.add_image(pic)
        if topic_id:
            dyn.set_topic(topic_id)
        if schedule_time > 0:
            dyn.set_send_time(schedule_time)
        result = await dynamic.send_dynamic(info=dyn, credential=cred)
        return {
            "success": True,
            "message": "动态发布成功",
            "data": result if isinstance(result, dict) else str(result),
        }

    async def send_message(self, receiver_uid: int, text: str) -> Dict[str, Any]:
        if not text or not text.strip():
            raise RuntimeError("text 不能为空")
        cred = await self.get_valid_credential()
        result = await session.send_msg(
            credential=cred,
            receiver_id=receiver_uid,
            msg_type=session.EventType.TEXT,
            content=text.strip(),
        )
        return {
            "success": True,
            "message": f"私信已发送给UID:{receiver_uid}",
            "data": result if isinstance(result, dict) else str(result),
        }
