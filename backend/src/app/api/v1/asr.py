"""ASR 签名端点 — 为前端生成讯飞 RTASR 的 WebSocket 签名 URL"""

import hashlib
import hmac
import time
import base64
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends

from src.core.config import get_settings
from .deps import get_current_username
from .models import ApiResponse

router = APIRouter(prefix="/asr", tags=["asr"])


def _generate_signa(appid: str, api_key: str, ts: str) -> str:
    """讯飞 RTASR 签名: Base64(HMAC-SHA1(MD5(appid + ts), api_key))"""
    base_string = appid + ts
    md5_digest = hashlib.md5(base_string.encode("utf-8")).hexdigest()
    signa = hmac.new(
        api_key.encode("utf-8"),
        md5_digest.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(signa).decode("utf-8")


@router.get("/sign")
async def get_asr_signed_url(
    _current_username: Annotated[str, Depends(get_current_username)],
) -> ApiResponse[dict]:
    """生成讯飞 RTASR WebSocket 签名 URL（需认证）

    返回的 URL 已启用角色分离（roleType=2），讯飞在返回结果中
    通过 rl 字段标识不同说话人编号。
    """
    cfg = get_settings().asr
    ts = str(int(time.time()))
    signa = _generate_signa(cfg.appid, cfg.api_key, ts)
    # base64 输出可能含 +/= 等字符，需 URL 编码
    signa_encoded = quote(signa, safe="")

    # vadMdn=2 使用近场模式，更符合双人围绕单设备采访的拾音场景。
    # roleType=2 启用角色分离，讯飞返回 rl 字段区分说话人。
    url = (
        f"wss://rtasr.xfyun.cn/v1/ws"
        f"?appid={cfg.appid}&ts={ts}&signa={signa_encoded}&vadMdn=2&roleType=2"
    )

    return ApiResponse(
        status="success",
        data={
            "url": url,
            "appid": cfg.appid,
            "expires_at": int(ts) + 300,
        },
    )
