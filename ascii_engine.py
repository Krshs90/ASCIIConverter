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
        self.realism_mode = False
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
    _saved_settings = None
    def apply_realism(self):
        self._saved_settings = {
            "char_set": self.current_char_set,
            "output_width": self.output_width,
            "brightness_boost": self.brightness_boost,
            "true_color_compensation": self.true_color_compensation,
            "color_mode": self.color_mode,
            "font_size": self.font.size if hasattr(self.font, 'size') else 12,
        }
        self.realism_mode = True
        self.set_char_set("Detailed")
        self.output_width = 250
        self.brightness_boost = 1.0
        self.true_color_compensation = True
        self.color_mode = "Original"
        self.set_font_size(8)
    def restore_from_realism(self):
        self.realism_mode = False
        if self._saved_settings:
            s = self._saved_settings
            self.set_char_set(s["char_set"])
            self.output_width = s["output_width"]
            self.brightness_boost = s["brightness_boost"]
            self.true_color_compensation = s["true_color_compensation"]
            self.color_mode = s["color_mode"]
            self.set_font_size(s["font_size"])
            self._saved_settings = None
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
            mean_brightness = arr.mean()
            tiles_with_brightness.append((mean_brightness, arr))
        tiles_with_brightness.sort(key=lambda x: x[0])
        self.char_tiles = np.array([t[1] for t in tiles_with_brightness])
        self.tile_brightness = np.array(
            [max(t[0], 0.01) for t in tiles_with_brightness], dtype=np.float32
        )
    def set_char_set(self, name):
        if name in self.char_sets and name != self.current_char_set:
            self.current_char_set = name
            self._precompute_tiles()
    def convert_frame_to_image(self, frame_bgr):
        if frame_bgr is None:
            return None
        char_tiles = self.char_tiles
        if char_tiles is None:
            return frame_bgr
        actual_char_height, actual_char_width = char_tiles.shape[1], char_tiles.shape[2]
        height, width, _ = frame_bgr.shape
        ratio = height / width
        new_width = self.output_width
        font_ratio = actual_char_height / actual_char_width
        new_height = int(new_width * ratio / font_ratio)
        if new_width <= 0 or new_height <= 0:
            return frame_bgr
        resized_img = cv2.resize(frame_bgr, (new_width, new_height))
        char_len = len(char_tiles)
        if self.true_color_compensation:
            return self._render_true_color(
                resized_img, char_tiles, char_len,
                new_width, new_height, actual_char_width, actual_char_height
            )
        else:
            return self._render_standard(
                resized_img, char_tiles, char_len,
                new_width, new_height, actual_char_width, actual_char_height
            )
    def _render_standard(self, resized_img, char_tiles, char_len,
                         new_width, new_height, actual_char_width, actual_char_height):
        gray_img = cv2.cvtColor(resized_img, cv2.COLOR_BGR2GRAY)
        if self.brightness_boost != 1.0:
            gray_img = np.clip(
                gray_img.astype(np.float32) * self.brightness_boost, 0, 255
            ).astype(np.uint8)
            resized_img = np.clip(
                resized_img.astype(np.float32) * self.brightness_boost, 0, 255
            ).astype(np.uint8)
        char_indices = np.clip(
            np.int32((gray_img / 255.0) * char_len), 0, char_len - 1
        )
        mapped_tiles = char_tiles[char_indices]
        if self.color_mode == "Original":
            colors = resized_img
        elif self.color_mode == "Grayscale":
            colors = np.stack((gray_img,) * 3, axis=-1)
        else:
            r, g, b = self.custom_color
            color_bgr = np.array([b, g, r], dtype=np.uint8)
            colors = np.full((new_height, new_width, 3), color_bgr, dtype=np.uint8)
        colored_tiles = (
            mapped_tiles[..., np.newaxis] * colors[:, :, np.newaxis, np.newaxis, :]
        )
        colored_tiles = colored_tiles.astype(np.uint8)
        stitched = colored_tiles.transpose(0, 2, 1, 3, 4)
        return stitched.reshape(
            new_height * actual_char_height, new_width * actual_char_width, 3
        )
    def _render_true_color(self, resized_img, char_tiles, char_len,
                           new_width, new_height, actual_char_width, actual_char_height):
        if self.brightness_boost != 1.0:
            resized_img = np.clip(
                resized_img.astype(np.float32) * self.brightness_boost, 0, 255
            ).astype(np.uint8)
        lab = cv2.cvtColor(resized_img, cv2.COLOR_BGR2LAB)
        lightness = lab[:, :, 0].astype(np.float32) / 255.0
        char_indices = np.clip(
            np.int32(lightness * char_len), 0, char_len - 1
        )
        mapped_tiles = char_tiles[char_indices]
        tile_bright_map = self.tile_brightness[char_indices]
        normalized_tiles = np.clip(
            mapped_tiles / tile_bright_map[:, :, np.newaxis, np.newaxis],
            0.0, 1.0
        )
        if self.color_mode == "Original":
            colors = resized_img
        elif self.color_mode == "Grayscale":
            gray_val = (lightness * 255).astype(np.uint8)
            colors = np.stack((gray_val,) * 3, axis=-1)
        else:
            r, g, b = self.custom_color
            colors = np.full(
                (new_height, new_width, 3), [b, g, r], dtype=np.uint8
            )
        colored_tiles = (
            normalized_tiles[..., np.newaxis]
            * colors[:, :, np.newaxis, np.newaxis, :].astype(np.float32)
        )
        colored_tiles = np.clip(colored_tiles, 0, 255).astype(np.uint8)
        stitched = colored_tiles.transpose(0, 2, 1, 3, 4)
        return stitched.reshape(
            new_height * actual_char_height, new_width * actual_char_width, 3
        )
