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
    def load_media(self, path_or_url, is_youtube=False):
        self.release()
        self.source_path = path_or_url
        source = path_or_url
        if is_youtube:
            ydl_opts = {
                'format': 'best[ext=mp4]', 
                'quiet': True,
                'no_warnings': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(path_or_url, download=False)
                source = info_dict.get('url', path_or_url)
        self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            return False
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if self.total_frames <= 1 and not is_youtube:
            self.is_video = False
        else:
            self.is_video = True
            if not is_youtube:
                try:
                    clip = VideoFileClip(self.source_path)
                    if clip.audio is not None:
                        self.audio_path = os.path.join(tempfile.gettempdir(), "ascii_temp_audio.mp3")
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
