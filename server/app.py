"""صالحة فيديو — محرّك التحميل (Hugging Face Space)"""
import os
import re
import shutil
import tempfile
from urllib.parse import quote

import yt_dlp
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

APP_KEY = os.environ.get("APP_KEY", "")
MAX_SIZE = 600 * 1024 * 1024  # 600MB

# كوكيز اختيارية (لإنستغرام مثلاً) — تُضاف كـ Secret باسم COOKIES
COOKIE_FILE = None
if os.environ.get("COOKIES"):
    COOKIE_FILE = "/tmp/cookies.txt"
    with open(COOKIE_FILE, "w") as f:
        f.write(os.environ["COOKIES"])

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Length"],
)


def check_key(request: Request):
    if not APP_KEY:
        return
    key = request.headers.get("x-key") or request.query_params.get("key")
    if key != APP_KEY:
        raise HTTPException(401, "مفتاح غير صحيح")


def base_opts():
    o = {"quiet": True, "no_warnings": True, "noplaylist": True}
    if COOKIE_FILE:
        o["cookiefile"] = COOKIE_FILE
    return o


def friendly_error(e: Exception) -> str:
    msg = str(e)
    if "login" in msg.lower() or "cookies" in msg.lower():
        return "المنصة تطلب تسجيل دخول لهذا الفيديو"
    if "Sign in to confirm" in msg:
        return "يوتيوب حظر الخادم مؤقتاً (تأكيد أنك لست روبوت)"
    if "Unsupported URL" in msg:
        return "هذا الرابط غير مدعوم"
    if "private" in msg.lower():
        return "الفيديو خاص أو محذوف"
    return "تعذّر جلب الفيديو: " + re.sub(r"\x1b\[[0-9;]*m", "", msg)[:200]


@app.get("/")
def root():
    return {"ok": True, "name": "salha-video", "yt_dlp": yt_dlp.version.__version__}


@app.get("/api/info")
def info(request: Request, url: str = Query(...)):
    check_key(request)
    try:
        with yt_dlp.YoutubeDL(base_opts()) as ydl:
            i = ydl.extract_info(url, download=False)
    except Exception as e:
        raise HTTPException(400, friendly_error(e))
    if i.get("_type") == "playlist" and i.get("entries"):
        i = next((x for x in i["entries"] if x), i)
    return {
        "title": i.get("title") or i.get("description") or "فيديو",
        "thumbnail": i.get("thumbnail"),
        "duration": i.get("duration"),
        "uploader": i.get("uploader") or i.get("channel") or "",
        "platform": i.get("extractor_key") or "",
    }


@app.get("/api/download")
def download(request: Request, url: str = Query(...), type: str = Query("video")):
    check_key(request)
    tmp = tempfile.mkdtemp(prefix="sv_")
    opts = base_opts()
    opts.update({
        "outtmpl": os.path.join(tmp, "%(title).80B.%(ext)s"),
        "max_filesize": MAX_SIZE,
        "restrictfilenames": False,
    })
    if type == "audio":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    else:
        # H.264 + AAC حتى يقبله تطبيق الصور في الآيفون
        opts["format"] = (
            "bv*[vcodec^=avc1][height<=1080]+ba[ext=m4a]/"
            "b[vcodec^=avc1][ext=mp4]/b[ext=mp4]/bv*+ba/b"
        )
        opts["merge_output_format"] = "mp4"
        opts["postprocessor_args"] = {"merger": ["-movflags", "+faststart"]}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HTTPException(400, friendly_error(e))

    files = [f for f in os.listdir(tmp) if not f.endswith((".part", ".ytdl"))]
    if not files:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HTTPException(400, "لم يتم إنشاء الملف")
    files.sort(key=lambda f: os.path.getsize(os.path.join(tmp, f)), reverse=True)
    path = os.path.join(tmp, files[0])
    name = files[0]
    media = "audio/mpeg" if name.endswith(".mp3") else "video/mp4"
    return FileResponse(
        path,
        media_type=media,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
        background=BackgroundTask(shutil.rmtree, tmp, ignore_errors=True),
    )
