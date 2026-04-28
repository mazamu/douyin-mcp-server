#!/usr/bin/env python3
"""
抖音视频文案提取器 WebUI

启动方式:
    cd douyin-mcp-server
    export API_KEY="sk-xxx"
    python web/app.py
    # 访问 http://localhost:8080
"""

import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "douyin-video" / "scripts"))

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn
import requests

# 导入抖音处理模块
from douyin_downloader import get_video_info, extract_text

# 导入文案拆分分析模块
sys.path.insert(0, str(Path(__file__).parent.parent / "douyin-video"))
from splitAndAnalyse import split_copywriting_batch
from urllib.parse import urlparse

app = FastAPI(title="抖音文案提取器", version="1.0.0")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


class VideoRequest(BaseModel):
    """视频请求模型"""
    url: str
    api_key: str = ""  # 可选，从前端传入


class VideoInfoResponse(BaseModel):
    """视频信息响应"""
    success: bool
    video_id: str = ""
    title: str = ""
    download_url: str = ""
    error: str = ""


class ExtractResponse(BaseModel):
    """文案提取响应"""
    success: bool
    video_id: str = ""
    title: str = ""
    text: str = ""
    download_url: str = ""
    error: str = ""


class AnalyzeRequest(BaseModel):
    """文案拆分分析请求"""
    transcripts: list  # [{"label": "文案A", "text": "..."}, ...]
    api_key: str = ""  # DeepSeek API Key


class AnalyzeResponse(BaseModel):
    """文案拆分分析响应"""
    success: bool
    result: dict = {}
    error: str = ""


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """主页面"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health_check():
    """健康检查"""
    api_key = os.getenv("API_KEY", "")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
    return {
        "status": "ok",
        "api_key_configured": bool(api_key),
        "deepseek_key_configured": bool(deepseek_key)
    }


@app.post("/api/video/info", response_model=VideoInfoResponse)
async def get_info(req: VideoRequest):
    """获取视频信息（无需 API_KEY）"""
    try:
        info = get_video_info(req.url)
        return VideoInfoResponse(
            success=True,
            video_id=info["video_id"],
            title=info["title"],
            download_url=info["url"]
        )
    except Exception as e:
        return VideoInfoResponse(success=False, error=str(e))


@app.post("/api/video/extract", response_model=ExtractResponse)
async def extract_transcript(req: VideoRequest):
    """提取视频文案（需要 API_KEY）"""
    # 优先使用请求中的 API Key，其次使用环境变量
    api_key = req.api_key or os.getenv("API_KEY", "")
    if not api_key:
        return ExtractResponse(
            success=False,
            error="请先配置 API Key"
        )

    try:
        result = extract_text(req.url, api_key=api_key, show_progress=False)
        return ExtractResponse(
            success=True,
            video_id=result["video_info"]["video_id"],
            title=result["video_info"]["title"],
            text=result["text"],
            download_url=result["video_info"]["url"]
        )
    except Exception as e:
        return ExtractResponse(success=False, error=str(e))


@app.post("/api/transcripts/analyze", response_model=AnalyzeResponse)
async def analyze_transcripts(req: AnalyzeRequest):
    """拆分分析文案结构（需要 DEEPSEEK_API_KEY）"""
    if not req.transcripts:
        return AnalyzeResponse(success=False, error="请提供至少一个文案")

    api_key = req.api_key or os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return AnalyzeResponse(
            success=False,
            error="请先配置 DeepSeek API Key"
        )

    try:
        copies = {t["label"]: t["text"] for t in req.transcripts}
        result = split_copywriting_batch(copies, api_key=api_key)
        return AnalyzeResponse(success=True, result=result)
    except Exception as e:
        return AnalyzeResponse(success=False, error=str(e))


def _get_referer_for_url(url: str) -> str:
    """根据视频 URL 自动判断来源平台，返回正确的 Referer"""
    domain = urlparse(url).hostname or ""
    if any(d in domain for d in ["douyin.com", "365yg.com", "amemv.com", "douyincdn.com",
                                  "iesdouyin.com", "douyinvod.com", "snssdk.com"]):
        return "https://www.douyin.com/"
    if any(d in domain for d in ["xiaohongshu.com", "xhscdn.com"]):
        return "https://www.xiaohongshu.com/"
    if any(d in domain for d in ["kuaishou.com", "kwai.com", "kscdn.com"]):
        return "https://www.kuaishou.com/"
    if any(d in domain for d in ["weibo.com", "weibocdn.com"]):
        return "https://www.weibo.com/"
    # 默认使用 URL 自身域名
    return f"https://{domain}/"


@app.get("/api/video/download")
async def download_video(url: str, filename: str = "video.mp4"):
    """代理下载视频（解决跨域和请求头问题）"""
    print(f"[Download] URL: {url}")
    print(f"[Download] Filename: {filename}")
    try:
        referer = _get_referer_for_url(url)

        download_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
            'Referer': referer,
            'Origin': referer.rstrip("/"),
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }

        response = requests.get(url, headers=download_headers, stream=True, allow_redirects=True, timeout=120)
        print(f"[Download] Response status: {response.status_code}")
        print(f"[Download] Referer: {referer}")
        response.raise_for_status()

        content_length = response.headers.get("content-length", "")

        def iter_content():
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        if content_length:
            headers["Content-Length"] = content_length

        return StreamingResponse(
            iter_content(),
            media_type="video/mp4",
            headers=headers
        )
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"下载失败: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def main():
    """启动服务"""
    port = int(os.getenv("PORT", "8080"))
    print(f"🚀 启动文案提取器 WebUI: http://localhost:{port}")
    print(f"📝 API_KEY 配置状态: {'已配置' if os.getenv('API_KEY') else '未配置'}")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
