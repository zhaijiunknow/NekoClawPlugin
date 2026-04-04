from __future__ import annotations

import base64
import json
import os
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from bilibili_api import Credential, comment, dynamic, favorite_list, hot, rank, search, session, user, video
from bilibili_api.login_v2 import QrCodeLogin, QrCodeLoginEvents
from bilibili_api.utils.picture import Picture


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
