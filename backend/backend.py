from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from urllib.parse import urlparse
import requests
import os
import uuid


app = FastAPI(title="Reel Downloader API")


# =========================
# CORS
# =========================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# SETTINGS
# =========================

DOWNLOAD_DIR = "downloads"

# Maximum allowed video size: 50 MB
MAX_FILE_SIZE = 50 * 1024 * 1024

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
import time


# =========================
# CLEAN OLD FILES
# =========================

FILE_EXPIRY_SECONDS = 30 * 60  # 30 minutes


def cleanup_old_files():

    current_time = time.time()

    for filename in os.listdir(DOWNLOAD_DIR):

        filepath = os.path.join(
            DOWNLOAD_DIR,
            filename
        )

        if not os.path.isfile(filepath):
            continue

        try:

            file_age = (
                current_time -
                os.path.getmtime(filepath)
            )

            if file_age > FILE_EXPIRY_SECONDS:

                os.remove(filepath)

        except OSError:

            pass

# =========================
# REQUEST MODEL
# =========================

class DownloadRequest(BaseModel):
    url: str


# =========================
# URL VALIDATION
# =========================

def is_valid_url(url: str):
    try:
        parsed = urlparse(url)

        return (
            parsed.scheme in ["http", "https"]
            and bool(parsed.netloc)
        )

    except Exception:
        return False


# =========================
# HOME
# =========================

@app.get("/")
def home():
    return {
        "status": "online",
        "message": "Video Downloader API is running"
    }


# =========================
# DOWNLOAD VIDEO
# =========================

@app.post("/download")
def download_video(data: DownloadRequest):

    url = data.url.strip()
    cleanup_old_files()
    # Validate URL
    if not is_valid_url(url):
        raise HTTPException(
            status_code=400,
            detail="Please enter a valid video URL."
        )

    filename = f"{uuid.uuid4().hex}.mp4"

    filepath = os.path.join(
        DOWNLOAD_DIR,
        filename
    )

    try:

        # Request video
        response = requests.get(
            url,
            stream=True,
            timeout=(10, 30),
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        # Check HTTP status
        response.raise_for_status()


        # =========================
        # CHECK CONTENT TYPE
        # =========================

        content_type = response.headers.get(
            "content-type",
            ""
        ).lower()

        if not content_type.startswith("video/"):

            raise HTTPException(
                status_code=400,
                detail="The URL does not point to a direct video file."
            )


        # =========================
        # CHECK CONTENT LENGTH
        # =========================

        content_length = response.headers.get(
            "content-length"
        )

        if content_length:

            try:

                content_length = int(
                    content_length
                )

            except ValueError:

                content_length = None


        if (
            content_length
            and content_length > MAX_FILE_SIZE
        ):

            raise HTTPException(
                status_code=413,
                detail="Video is too large. Maximum size is 50 MB."
            )


        # =========================
        # DOWNLOAD
        # =========================

        downloaded_size = 0

        with open(filepath, "wb") as file:

            for chunk in response.iter_content(
                chunk_size=1024 * 1024
            ):

                if not chunk:
                    continue


                downloaded_size += len(chunk)


                # Check actual downloaded size
                if downloaded_size > MAX_FILE_SIZE:

                    # Close/delete partial file
                    file.close()

                    if os.path.exists(filepath):
                        os.remove(filepath)

                    raise HTTPException(
                        status_code=413,
                        detail="Video is too large. Maximum size is 50 MB."
                    )


                file.write(chunk)


        # =========================
        # SUCCESS
        # =========================

        return {
            "success": True,
            "filename": filename,
            "download_url": f"/files/{filename}"
        }


    except HTTPException:

        # Delete incomplete file if it exists
        if os.path.exists(filepath):
            os.remove(filepath)

        raise


    except requests.RequestException:

        # Delete incomplete file
        if os.path.exists(filepath):
            os.remove(filepath)

        raise HTTPException(
            status_code=400,
            detail="Unable to access the video URL."
        )


    except Exception:

        # Delete incomplete file
        if os.path.exists(filepath):
            os.remove(filepath)

        raise HTTPException(
            status_code=500,
            detail="Something went wrong while downloading the video."
        )


# =========================
# GET DOWNLOADED FILE
# =========================

@app.get("/files/{filename}")
def get_file(filename: str):

    filepath = os.path.join(
        DOWNLOAD_DIR,
        filename
    )


    if not os.path.exists(filepath):

        raise HTTPException(
            status_code=404,
            detail="File not found."
        )


    return FileResponse(
        filepath,
        media_type="video/mp4",
        filename=filename
    )