FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

COPY --chown=user app.py .

# تحديث yt-dlp عند كل تشغيل لأن المنصات تتغيّر باستمرار
CMD pip install --no-cache-dir -q -U yt-dlp; uvicorn app:app --host 0.0.0.0 --port ${PORT:-7860}
