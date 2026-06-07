import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
class AsciiEngine:
    def __init__(self):
        self.char_sets = {
            "Standard": "@%#*+=-:. ",
            "Detailed": "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. ",
            "Blocks": "█▓▒░ ",
            "Binary": "10 "
        }
        self.current_char_set = "Standard"
        self.color_mode = "Original" 
        self.custom_color = (0, 255, 0) 
        self.bg_color = (0, 0, 0)
        self.output_width = 100 
        self.brightness_boost = 1.0 
        self.true_color_compensation = False
        self.tile_brightness = None
        try:
            self.font = ImageFont.truetype("consola.ttf", 12)
        except IOError:
            self.font = ImageFont.load_default()
        self.char_width = 7
        self.char_height = 14
        self._update_font_metrics()
        self.char_tiles = None
        self._precompute_tiles()
    def _update_font_metrics(self):
        try:
            bbox = self.font.getbbox("A")
            self.char_width = bbox[2] - bbox[0]
            self.char_height = bbox[3] - bbox[1]
            if self.char_width <= 0: self.char_width = 7
            if self.char_height <= 0: self.char_height = 14
        except Exception:
            self.char_width = 7
            self.char_height = 14
    def set_font_size(self, size):
        try:
            self.font = ImageFont.truetype("consola.ttf", size)
            self._update_font_metrics()
            self._precompute_tiles() 
        except IOError:
            pass
    def _precompute_tiles(self):
        chars = self.char_sets.get(self.current_char_set, self.char_sets["Standard"])
        tiles_with_brightness = []
        for char in chars:
            img = Image.new("L", (self.char_width, self.char_height), 0)
            draw = ImageDraw.Draw(img)
            draw.text((0, 0), char, font=self.font, fill=255)
            arr = np.array(img, dtype=np.float32) / 255.0
            tiles_with_brightness.append((arr.mean(), arr))
        tiles_with_brightness.sort(key=lambda x: x[0])
        self.char_tiles = np.array([t[1] for t in tiles_with_brightness])
        self.tile_brightness = np.array([max(t[0], 0.05) for t in tiles_with_brightness], dtype=np.float32)
    def set_char_set(self, name):
        if name in self.char_sets and name != self.current_char_set:
            self.current_char_set = name
            self._precompute_tiles()
    def convert_frame_to_image(self, frame_bgr):
        if frame_bgr is None:
            return None
        height, width, _ = frame_bgr.shape
        ratio = height / width
        new_width = self.output_width
        font_ratio = self.char_height / self.char_width
        new_height = int(new_width * ratio / font_ratio)
        if new_width <= 0 or new_height <= 0:
            return frame_bgr
            
        if self.true_color_compensation:
            resized_img = cv2.resize(frame_bgr, (new_width, new_height), interpolation=cv2.INTER_NEAREST)
            hsv = cv2.cvtColor(resized_img, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.5, 0, 255)
            hsv[:, :, 2] = np.clip(hsv[:, :, 2] * 1.5, 0, 255)
            resized_img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
        else:
            resized_img = cv2.resize(frame_bgr, (new_width, new_height))
            
        gray_img = cv2.cvtColor(resized_img, cv2.COLOR_BGR2GRAY)
        if self.brightness_boost != 1.0:
            gray_img = np.clip(gray_img.astype(np.float32) * self.brightness_boost, 0, 255).astype(np.uint8)
            resized_img = np.clip(resized_img.astype(np.float32) * self.brightness_boost, 0, 255).astype(np.uint8)
        char_len = len(self.char_tiles)
        char_indices = np.clip(np.int32((gray_img / 255.0) * char_len), 0, char_len - 1)
        mapped_tiles = self.char_tiles[char_indices]
        if self.color_mode == "Original":
            colors = resized_img 
        elif self.color_mode == "Grayscale":
            colors = np.stack((gray_img,)*3, axis=-1)
        else: 
            r, g, b = self.custom_color
            color_bgr = np.array([b, g, r], dtype=np.uint8)
            colors = np.full((new_height, new_width, 3), color_bgr, dtype=np.uint8)
            
        colored_tiles = mapped_tiles[..., np.newaxis] * colors[:, :, np.newaxis, np.newaxis, :]
        colored_tiles = colored_tiles.astype(np.uint8)
        stitched = colored_tiles.transpose(0, 2, 1, 3, 4)
        out_frame_bgr = stitched.reshape(new_height * self.char_height, new_width * self.char_width, 3)
        return out_frame_bgr
