import os
import re
import json
import time
import subprocess
import yt_dlp
from faster_whisper import WhisperModel
import google.generativeai as genai
from typing import Optional, List, Dict, Any

class YouTubeProcessor:
    def __init__(self, api_key: str):
        self.api_key = api_key
        genai.configure(api_key=self.api_key)
        self.model_whisper = None  # Lazy load
        self.proxies = self._load_proxies()

    def _load_proxies(self) -> List[str]:
        proxy_path = os.path.join(os.path.dirname(__file__), "proxies.txt")
        if not os.path.exists(proxy_path):
            return []
        try:
            with open(proxy_path, "r", encoding="utf-8") as f:
                proxies = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            print(f"Loaded {len(proxies)} proxies from {proxy_path}")
            return proxies
        except Exception as e:
            print(f"Failed to load proxies: {e}")
            return []

    def _get_random_proxy(self) -> Optional[str]:
        if not self.proxies:
            return None
        import random
        return random.choice(self.proxies)

    def extract_timestamp_and_clean_title(self, full_title: str):
        match = re.search(r'(_\d{14})$', full_title)
        if match:
            timestamp = match.group(1)
            cleaned_title = full_title[:match.start()]
            return cleaned_title.strip(), timestamp
        return full_title, None

    def download_video(self, url: str, output_path: str = "temp_video.mp4") -> (Optional[str], Optional[str], Optional[str]):
        ydl_opts = {
            'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
            'outtmpl': output_path,
            'overwrites': True,
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'preference': 'js-runtimes:node', # 強制使用 Node.js 進行 JS 解密
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}}, # 優先嘗試 android (最寬鬆) 與 web 客戶端
            'socket_timeout': 30, # 30 秒連線超時，避免卡死
        }
        
        # 如果存在 cookies.txt，則使用它來繞過機器人偵測
        cookie_path = os.path.join(os.path.dirname(__file__), "cookies.txt")
        if os.path.exists(cookie_path):
            ydl_opts['cookiefile'] = cookie_path
        
        # 使用隨機 Proxy
        proxy = self._get_random_proxy()
        if proxy:
            print(f"Using proxy: {proxy}")
            ydl_opts['proxy'] = proxy

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_title = info.get('title', '未知影片')
            return output_path, video_title, None
        except Exception as e:
            error_msg = str(e)
            print(f"下載失敗: {error_msg}")
            return None, None, error_msg

    def extract_audio(self, video_path: str, audio_output_path: str) -> Optional[str]:
        command = [
            'ffmpeg', '-y', '-i', video_path, '-vn',
            '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
            audio_output_path
        ]
        try:
            subprocess.run(command, check=True, capture_output=True)
            return audio_output_path
        except Exception as e:
            print(f"提取音訊失敗: {e}")
            return None

    def generate_subtitles(self, audio_path: str, model_size: str = "large-v3") -> Optional[str]:
        output_srt_path = audio_path.replace('.wav', '.srt')
        try:
            if self.model_whisper is None:
                self.model_whisper = WhisperModel(model_size, device="cpu", compute_type="int8")
            
            segments, info = self.model_whisper.transcribe(audio_path, beam_size=5, language='zh')
            
            segment_id = 1
            with open(output_srt_path, "w", encoding="utf-8") as srt_file:
                for segment in segments:
                    start_ms = int(segment.start * 1000)
                    end_ms = int(segment.end * 1000)
                    start_time = f"{start_ms // 3600000:02}:{(start_ms // 60000) % 60:02}:{(start_ms // 1000) % 60:02},{start_ms % 1000:03}"
                    end_time = f"{end_ms // 3600000:02}:{(end_ms // 60000) % 60:02}:{(end_ms // 1000) % 60:02},{end_ms % 1000:03}"
                    srt_file.write(f"{segment_id}\n{start_time} --> {end_time}\n{segment.text.strip()}\n\n")
                    segment_id += 1
            return output_srt_path
        except Exception as e:
            print(f"生成字幕失敗: {e}")
            return None

    def analyze_video(self, video_path: str, context: str) -> Optional[Dict[str, Any]]:
        try:
            video_file = genai.upload_file(path=video_path)
            start_time = time.time()
            while video_file.state.name == "PROCESSING":
                if time.time() - start_time > 600: # 10 分鐘超時
                    raise TimeoutError("Gemini 影片處理超時")
                time.sleep(5)
                video_file = genai.get_file(video_file.name)
            
            if video_file.state.name == "FAILED":
                return None

            model = genai.GenerativeModel(model_name="gemini-2.5-flash")
            prompt = f"""
            你是一位專業的遊戲 YouTuber。這是一段《{context}》的純遊戲畫面。
            請分析畫面內容，並輸出一個純 JSON 物件 (不要 Markdown)，包含：
            1. "title": 一個繁體中文標題 (包含遊戲名、Boss名或重要事件)。
            2. "description": 150字左右的影片描述，包含 SEO 關鍵字。
            3. "tags": 5-8 個標籤 (逗號分隔字串)。
            4. "chapters": 一個字串列表，每行格式為 "MM:SS - 章節名稱"。
            格式範例：
            {{
              "title": "...",
              "description": "...",
              "tags": "tag1, tag2",
              "chapters": ["00:00 - 開始", "02:15 - Boss戰"]
            }}
            """
            response = model.generate_content([video_file, prompt])
            text = response.text.replace('```json', '').replace('```', '').strip()
            if text.startswith("json"): text = text[4:]
            return json.loads(text)
        except Exception as e:
            print(f"AI 分析失敗: {e}")
            return None
