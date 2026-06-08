import cv2
import yt_dlp
import os
import tempfile
from moviepy import VideoFileClip
import math
class MediaHandler:
    def __init__(self):
        self.cap = None
        self.fps = 30
        self.total_frames = 0
        self.current_frame_idx = 0
        self.is_video = False
        self.has_audio = False
        self.audio_path = None
        self.source_path = None
    def load_media(self, path_or_url, is_youtube=False, progress_callback=None):
        self.release()
        self.source_path = path_or_url
        source = path_or_url
        
        import uuid
        ext = os.path.splitext(path_or_url)[1].lower()
        if not is_youtube and ext in ['.png', '.jpg', '.jpeg', '.bmp', '.webp']:
            img = cv2.imread(path_or_url)
            if img is not None:
                self.single_image = img
                self.is_video = False
                self.total_frames = 1
                self.fps = 0
                self.current_frame_idx = 0
                self.has_audio = False
                return True
                
        if is_youtube:
            # Strip tracking parameters which can sometimes confuse the extractor
            if '?si=' in path_or_url:
                path_or_url = path_or_url.split('?si=')[0]
                
            uid = uuid.uuid4().hex[:8]
            video_out = os.path.join(tempfile.gettempdir(), f"ascii_temp_video_{uid}.mp4")
            
            def yt_progress_hook(d):
                if d['status'] == 'downloading':
                    p = d.get('_percent_str', '0.0%')
                    if progress_callback:
                        progress_callback(f"Downloading Video... {p.strip()}")
                        
            retry_strategies = [
                {'format': 'best[ext=mp4]/best', 'extractor_args': {'youtube': {'player_client': ['web', 'default']}}},
                {'format': 'best[ext=mp4]/best', 'extractor_args': {'youtube': {'player_client': ['android']}}},
                {'format': 'best[ext=mp4]/best', 'extractor_args': {'youtube': {'player_client': ['tv']}}},
                {'format': 'best[ext=mp4]/best'}
            ]
            
            success = False
            last_error = None
            self.successful_youtube_strategy = None
            
            for strategy in retry_strategies:
                ydl_opts = {
                    'format': strategy['format'], 
                    'outtmpl': video_out,
                    'quiet': True,
                    'no_warnings': True,
                    'progress_hooks': [yt_progress_hook]
                }
                if 'extractor_args' in strategy:
                    ydl_opts['extractor_args'] = strategy['extractor_args']
                    
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([path_or_url])
                        if os.path.exists(video_out):
                            source = video_out
                            self.source_path = source
                            success = True
                            self.successful_youtube_strategy = strategy
                            break
                except Exception as e:
                    last_error = e
                    continue
                    
            if not success:
                raise Exception(f"YouTube is blocking the extraction. We tried multiple methods but YouTube's anti-bot protection blocked all of them. This is not a bug on our end, try again later or use a different video. (Sometimes restarting the application helps reset the connection.)\n\nLast error: {last_error}")
        self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            return False
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if self.total_frames <= 1 and not is_youtube:
            self.is_video = False
            ret, frame = self.cap.read()
            if ret:
                self.single_image = frame
        else:
            self.is_video = True
            
            uid = uuid.uuid4().hex[:8]
            self.audio_path = os.path.join(tempfile.gettempdir(), f"ascii_temp_audio_{uid}.wav")
            
            if progress_callback:
                progress_callback("Extracting audio... please wait.")
                
            try:
                clip = VideoFileClip(source)
                if clip.audio is not None:
                    clip.audio.write_audiofile(self.audio_path, logger=None)
                    self.has_audio = True
                clip.close()
            except Exception as e:
                print(f"Audio extraction failed or no audio: {e}")
                self.has_audio = False
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.fps <= 0 or math.isnan(self.fps):
            self.fps = 30 
        self.current_frame_idx = 0
        return True

    def get_next_frame(self):
        if not self.is_video and hasattr(self, 'single_image'):
            return True, self.single_image.copy()
        if self.cap is None or not self.cap.isOpened():
            return False, None
        ret, frame = self.cap.read()
        if ret:
            self.current_frame_idx += 1
        return ret, frame

    def get_frame_position(self):
        if self.cap is not None and self.is_video:
            return int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
        return 0

    def set_frame_position(self, frame_idx):
        if self.cap is not None and self.is_video:
            if 0 <= frame_idx < self.total_frames:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                self.current_frame_idx = frame_idx
    def reset(self):
        self.set_frame_position(0)
    def release(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.is_video = False
        self.fps = 30
        self.total_frames = 0
        self.has_audio = False
        if getattr(self, 'audio_path', None) and os.path.exists(self.audio_path):
            try:
                os.remove(self.audio_path)
            except:
                pass
        self.audio_path = None
        
        if getattr(self, 'source_path', None) and isinstance(self.source_path, str) and 'ascii_temp_video_' in self.source_path and os.path.exists(self.source_path):
            try:
                os.remove(self.source_path)
            except:
                pass
