import os
import uuid
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from processor import YouTubeProcessor

load_dotenv()

app = FastAPI(title="YouTube Helper API")

# 允許跨域請求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

processor = YouTubeProcessor(api_key=os.getenv("GEMINI_API_KEY", ""))

# 模擬資料庫儲存任務狀態
jobs: Dict[str, Any] = {}

class ProcessRequest(BaseModel):
    url: str
    generate_subtitles: bool = False

async def run_pipeline(job_id: str, url: str, need_subtitles: bool):
    jobs[job_id]["status"] = "downloading"
    video_path = f"temp_{job_id}.mp4"
    
    path, title, error = processor.download_video(url, video_path)
    if not path:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = f"下載影片失敗: {error}" if error else "下載影片失敗"
        return

    jobs[job_id]["status"] = "analyzing"
    cleaned_title, timestamp = processor.extract_timestamp_and_clean_title(title)
    analysis = processor.analyze_video(path, cleaned_title)
    
    if analysis:
        if timestamp:
            analysis["title"] = f"{analysis['title']}{timestamp}"
        jobs[job_id]["result"] = analysis
    else:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = "AI 分析失敗"
        return

    if need_subtitles:
        jobs[job_id]["status"] = "transcribing"
        audio_path = f"temp_{job_id}.wav"
        if processor.extract_audio(path, audio_path):
            srt_path = processor.generate_subtitles(audio_path)
            if srt_path:
                with open(srt_path, "r", encoding="utf-8") as f:
                    jobs[job_id]["result"]["subtitles"] = f.read()
                os.remove(srt_path)
            if os.path.exists(audio_path): os.remove(audio_path)

    # 清理影片檔
    if os.path.exists(path): os.remove(path)
    
    jobs[job_id]["status"] = "completed"

@app.post("/process")
async def process_video(request: ProcessRequest, background_tasks: BackgroundTasks):
    if not processor.api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY 未設定")
    
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "pending", "result": None}
    
    background_tasks.add_task(run_pipeline, job_id, request.url, request.generate_subtitles)
    
    return {"job_id": job_id}

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="找不到任務")
    return jobs[job_id]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
