import sys
import numpy as np
from PyQt6.QtWidgets import QApplication
from main import AsciiApp
from ascii_engine import AsciiEngine
from media_handler import MediaHandler
import qdarktheme
def test_engine():
    print("Testing AsciiEngine...")
    engine = AsciiEngine()
    frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
    out = engine.convert_frame_to_image(frame)
    print(f"Standard output shape: {out.shape}")
    engine.output_width = 150
    engine.color_mode = "Custom"
    engine.custom_color = (255, 0, 0)
    out = engine.convert_frame_to_image(frame)
    print(f"Custom output shape: {out.shape}")
    print("AsciiEngine test PASSED.")
def test_media_handler():
    print("Testing MediaHandler...")
    handler = MediaHandler()
    assert not handler.is_video
    print("MediaHandler instantiation PASSED.")
def test_gui():
    print("Testing GUI Initialization...")
    app = QApplication(sys.argv)
    window = AsciiApp()
    print("GUI Init PASSED.")
if __name__ == "__main__":
    test_engine()
    test_media_handler()
    test_gui()
    print("ALL TESTS PASSED.")
