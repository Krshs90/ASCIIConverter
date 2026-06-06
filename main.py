import sys
import cv2
import numpy as np
import time
import os
import tempfile
import pygame
from moviepy import VideoFileClip, AudioFileClip
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                             QComboBox, QSpinBox, QFileDialog, QGroupBox, QColorDialog,
                             QMessageBox, QSlider, QStyle, QCheckBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QPainter
import qdarktheme
from ascii_engine import AsciiEngine
from media_handler import MediaHandler
class VideoDisplay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = None
        self.text = "Load media to begin."
    def set_image(self, qt_img):
        self.image = qt_img
        self.text = ""
        self.update()
    def set_text(self, text):
        self.image = None
        self.text = text
        self.update()
    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.rect()
        if self.image:
            scaled_img = self.image.scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            x = (rect.width() - scaled_img.width()) // 2
            y = (rect.height() - scaled_img.height()) // 2
            painter.drawImage(x, y, scaled_img)
        elif self.text:
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text)
class VideoProcessingThread(QThread):
    frame_ready_signal = pyqtSignal()
    playback_finished_signal = pyqtSignal()
    progress_signal = pyqtSignal(int)
    def __init__(self, media_handler, ascii_engine):
        super().__init__()
        self._run_flag = True
        self.media_handler = media_handler
        self.ascii_engine = ascii_engine
        self.is_paused = False
        self.is_looping = False
        self.latest_frame = None
        self.seek_request = None
    def run(self):
        target_delay = 1.0 / self.media_handler.fps if self.media_handler.fps > 0 else 0.033
        while self._run_flag:
            start_time = time.time()
            if self.seek_request is not None:
                self.media_handler.set_frame_position(self.seek_request)
                self.seek_request = None
            if not self.is_paused:
                ret, frame = self.media_handler.get_next_frame()
                if ret:
                    ascii_bgr = self.ascii_engine.convert_frame_to_image(frame)
                    if ascii_bgr is not None:
                        rgb_image = cv2.cvtColor(ascii_bgr, cv2.COLOR_BGR2RGB)
                        h, w, ch = rgb_image.shape
                        bytes_per_line = ch * w
                        qt_format = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                        self.latest_frame = qt_format.copy()
                        self.frame_ready_signal.emit()
                    self.progress_signal.emit(self.media_handler.current_frame_idx)
                    if not self.media_handler.is_video:
                        self._run_flag = False
                        break
                    elapsed = time.time() - start_time
                    sleep_time = target_delay - elapsed
                    if sleep_time > 0:
                        self.msleep(int(sleep_time * 1000))
                    else:
                        self.msleep(1) 
                else:
                    if self.is_looping and self.media_handler.is_video:
                        self.media_handler.reset()
                        continue
                    self.playback_finished_signal.emit()
                    self._run_flag = False
                    break
            else:
                self.msleep(50)
    def stop(self):
        self._run_flag = False
        self.wait()
class AsciiApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ASCII Art Converter V2")
        self.resize(1100, 800)
        self.ascii_engine = AsciiEngine()
        self.media_handler = MediaHandler()
        self.video_thread = None
        self.is_scrubbing = False
        pygame.mixer.init()
        self.init_ui()
    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        top_layout = QHBoxLayout()
        left_panel = QVBoxLayout()
        load_group = QGroupBox("Load Media")
        load_layout = QVBoxLayout()
        self.btn_load_file = QPushButton("Load Image/Video")
        self.btn_load_file.clicked.connect(self.load_file)
        load_layout.addWidget(self.btn_load_file)
        yt_layout = QHBoxLayout()
        self.txt_yt_url = QLineEdit()
        self.txt_yt_url.setPlaceholderText("YouTube URL...")
        self.btn_load_yt = QPushButton("Fetch")
        self.btn_load_yt.clicked.connect(self.load_youtube)
        yt_layout.addWidget(self.txt_yt_url)
        yt_layout.addWidget(self.btn_load_yt)
        load_layout.addLayout(yt_layout)
        load_group.setLayout(load_layout)
        left_panel.addWidget(load_group)
        settings_group = QGroupBox("Appearance Settings")
        settings_layout = QVBoxLayout()
        settings_layout.addWidget(QLabel("Character Set:"))
        self.cb_charset = QComboBox()
        self.cb_charset.addItems(self.ascii_engine.char_sets.keys())
        self.cb_charset.currentTextChanged.connect(self.change_charset)
        settings_layout.addWidget(self.cb_charset)
        settings_layout.addWidget(QLabel("Color Mode:"))
        self.cb_colormode = QComboBox()
        self.cb_colormode.addItems(["Original", "Grayscale", "Custom"])
        self.cb_colormode.currentTextChanged.connect(self.change_colormode)
        settings_layout.addWidget(self.cb_colormode)
        self.btn_custom_color = QPushButton("Pick Custom Color")
        self.btn_custom_color.clicked.connect(self.pick_color)
        self.btn_custom_color.setEnabled(False)
        settings_layout.addWidget(self.btn_custom_color)
        detail_layout = QHBoxLayout()
        detail_layout.addWidget(QLabel("Detail Level:"))
        self.lbl_detail_val = QLabel("100")
        detail_layout.addStretch()
        detail_layout.addWidget(self.lbl_detail_val)
        settings_layout.addLayout(detail_layout)
        self.slider_detail = QSlider(Qt.Orientation.Horizontal)
        self.slider_detail.setRange(20, 300)
        self.slider_detail.setValue(100)
        self.slider_detail.valueChanged.connect(self.change_detail)
        settings_layout.addWidget(self.slider_detail)
        bright_layout = QHBoxLayout()
        bright_layout.addWidget(QLabel("Brightness Boost:"))
        self.lbl_bright_val = QLabel("1.0x")
        bright_layout.addStretch()
        bright_layout.addWidget(self.lbl_bright_val)
        settings_layout.addLayout(bright_layout)
        self.slider_bright = QSlider(Qt.Orientation.Horizontal)
        self.slider_bright.setRange(10, 50) 
        self.slider_bright.setValue(10)
        self.slider_bright.valueChanged.connect(self.change_brightness)
        settings_layout.addWidget(self.slider_bright)
        settings_layout.addWidget(QLabel("Font Size:"))
        self.sb_font = QSpinBox()
        self.sb_font.setRange(6, 36)
        self.sb_font.setValue(12)
        self.sb_font.valueChanged.connect(self.change_font_size)
        settings_layout.addWidget(self.sb_font)
        self.btn_reset = QPushButton("Reset to Defaults")
        self.btn_reset.clicked.connect(self.reset_settings)
        settings_layout.addWidget(self.btn_reset)
        settings_group.setLayout(settings_layout)
        left_panel.addWidget(settings_group)
        self.btn_export = QPushButton("Export Video to MP4")
        self.btn_export.clicked.connect(self.export_video)
        left_panel.addWidget(self.btn_export)
        left_panel.addStretch()
        right_panel = QVBoxLayout()
        self.video_display = VideoDisplay()
        self.video_display.setSizePolicy(
            self.video_display.sizePolicy().Policy.Expanding,
            self.video_display.sizePolicy().Policy.Expanding
        )
        right_panel.addWidget(self.video_display)
        top_layout.addLayout(left_panel)
        top_layout.addLayout(right_panel, 1)
        main_layout.addLayout(top_layout, 1)
        bottom_layout = QHBoxLayout()
        self.btn_play = QPushButton()
        self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.btn_play.clicked.connect(self.toggle_play)
        bottom_layout.addWidget(self.btn_play)
        self.btn_stop = QPushButton()
        self.btn_stop.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self.btn_stop.clicked.connect(self.stop_video)
        bottom_layout.addWidget(self.btn_stop)
        self.lbl_time = QLabel("00:00 / 00:00")
        bottom_layout.addWidget(self.lbl_time)
        self.cb_loop = QCheckBox("Loop")
        self.cb_loop.stateChanged.connect(self.toggle_loop)
        bottom_layout.addWidget(self.cb_loop)
        self.cb_mute = QCheckBox("Mute Audio")
        self.cb_mute.stateChanged.connect(self.toggle_mute)
        bottom_layout.addWidget(self.cb_mute)
        self.slider_progress = QSlider(Qt.Orientation.Horizontal)
        self.slider_progress.setEnabled(False)
        self.slider_progress.sliderPressed.connect(self.scrub_start)
        self.slider_progress.sliderMoved.connect(self.scrub_move)
        self.slider_progress.sliderReleased.connect(self.scrub_end)
        bottom_layout.addWidget(self.slider_progress)
        main_layout.addLayout(bottom_layout)
    def load_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Media File", "", "Video/Image Files (*.mp4 *.avi *.mkv *.png *.jpg *.jpeg)")
        if file_name:
            self.stop_video()
            if self.media_handler.load_media(file_name):
                self.setup_playback()
            else:
                QMessageBox.critical(self, "Error", "Could not load media file.")
    def load_youtube(self):
        url = self.txt_yt_url.text().strip()
        if url:
            self.stop_video()
            self.video_display.set_text("Fetching YouTube stream... please wait.")
            QApplication.processEvents()
            try:
                if self.media_handler.load_media(url, is_youtube=True):
                    self.setup_playback()
                else:
                    QMessageBox.critical(self, "Error", "Could not fetch YouTube stream.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load YouTube video: {e}")
                self.video_display.set_text("Load media to begin.")
    def setup_playback(self):
        if self.media_handler.is_video:
            self.slider_progress.setEnabled(True)
            self.slider_progress.setRange(0, self.media_handler.total_frames)
        else:
            self.slider_progress.setEnabled(False)
            self.lbl_time.setText("--:-- / --:--")
        self.play_video()
    def reset_settings(self):
        self.cb_charset.setCurrentText("Standard")
        self.cb_colormode.setCurrentText("Original")
        self.slider_detail.setValue(100)
        self.slider_bright.setValue(10)
        self.cb_loop.setChecked(False)
        self.sb_font.setValue(12)
    def toggle_mute(self, state):
        if state == 2: 
            pygame.mixer.music.set_volume(0.0)
        else:
            pygame.mixer.music.set_volume(1.0)
    def change_charset(self, text):
        self.ascii_engine.set_char_set(text)
    def change_colormode(self, text):
        self.ascii_engine.color_mode = text
        self.btn_custom_color.setEnabled(text == "Custom")
    def pick_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.ascii_engine.custom_color = (color.red(), color.green(), color.blue())
    def change_detail(self, val):
        self.lbl_detail_val.setText(str(val))
        self.ascii_engine.output_width = val
    def change_brightness(self, val):
        mult = val / 10.0
        self.lbl_bright_val.setText(f"{mult:.1f}x")
        self.ascii_engine.brightness_boost = mult
    def change_font_size(self, val):
        self.ascii_engine.set_font_size(val)
    def toggle_play(self):
        if self.video_thread is None:
            self.play_video()
        elif self.video_thread.is_paused:
            self.video_thread.is_paused = False
            self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
            if pygame.mixer.music.get_busy() or self.media_handler.has_audio:
                pygame.mixer.music.unpause()
        else:
            self.video_thread.is_paused = True
            self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            if pygame.mixer.music.get_busy() or self.media_handler.has_audio:
                pygame.mixer.music.pause()
    def toggle_loop(self, state):
        if self.video_thread is not None:
            self.video_thread.is_looping = (state == 2) 
    def play_video(self):
        if self.video_thread is not None and not self.video_thread._run_flag:
            self.video_thread = None
        if self.video_thread is None:
            self.video_thread = VideoProcessingThread(self.media_handler, self.ascii_engine)
            self.video_thread.is_looping = self.cb_loop.isChecked()
            self.video_thread.frame_ready_signal.connect(self.update_image)
            self.video_thread.playback_finished_signal.connect(self.on_playback_finished)
            self.video_thread.progress_signal.connect(self.update_progress)
            self.video_thread.start()
            if self.media_handler.has_audio and self.media_handler.audio_path:
                try:
                    pygame.mixer.music.load(self.media_handler.audio_path)
                    pos_sec = self.media_handler.current_frame_idx / self.media_handler.fps if self.media_handler.fps > 0 else 0
                    pygame.mixer.music.play(loops=-1 if self.cb_loop.isChecked() else 0, start=pos_sec)
                    if self.cb_mute.isChecked():
                        pygame.mixer.music.set_volume(0.0)
                    else:
                        pygame.mixer.music.set_volume(1.0)
                except Exception as e:
                    print(f"Audio playback error: {e}")
            self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
    def stop_video(self):
        if self.video_thread is not None:
            self.video_thread.stop()
            self.video_thread = None
        self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        pygame.mixer.music.stop()
        self.slider_progress.setValue(0)
        self.update_time_label(0)
    def scrub_start(self):
        self.is_scrubbing = True
        if self.video_thread is not None:
            self.video_thread.is_paused = True
    def scrub_move(self, position):
        self.update_time_label(position)
    def scrub_end(self):
        self.is_scrubbing = False
        position = self.slider_progress.value()
        if self.video_thread is not None:
            self.video_thread.seek_request = position
            self.video_thread.is_paused = False
            if self.media_handler.has_audio:
                pos_sec = position / self.media_handler.fps if self.media_handler.fps > 0 else 0
                try:
                    pygame.mixer.music.set_pos(pos_sec)
                    pygame.mixer.music.unpause()
                except Exception:
                    pass
        else:
            self.media_handler.set_frame_position(position)
            if self.media_handler.has_audio:
                pos_sec = position / self.media_handler.fps if self.media_handler.fps > 0 else 0
                try:
                    pygame.mixer.music.play(start=pos_sec)
                    pygame.mixer.music.pause()
                except Exception:
                    pass
    def update_progress(self, frame_idx):
        if not self.is_scrubbing:
            self.slider_progress.setValue(frame_idx)
            self.update_time_label(frame_idx)
    def update_time_label(self, current_frame):
        if self.media_handler.fps > 0 and self.media_handler.is_video:
            current_sec = int(current_frame / self.media_handler.fps)
            total_sec = int(self.media_handler.total_frames / self.media_handler.fps)
            curr_str = f"{current_sec // 60:02d}:{current_sec % 60:02d}"
            tot_str = f"{total_sec // 60:02d}:{total_sec % 60:02d}"
            self.lbl_time.setText(f"{curr_str} / {tot_str}")
    def update_image(self):
        if self.video_thread and self.video_thread.latest_frame:
            self.video_display.set_image(self.video_thread.latest_frame)
    def on_playback_finished(self):
        self.stop_video()
    def export_video(self):
        if not self.media_handler.is_video:
            QMessageBox.information(self, "Info", "Load a video first to export.")
            return
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Video", "", "MP4 Video (*.mp4)")
        if not save_path:
            return
        self.stop_video()
        self.media_handler.reset()
        self.video_display.set_text("Exporting video... please wait. App will freeze until done.")
        QApplication.processEvents()
        ret, frame = self.media_handler.get_next_frame()
        if not ret:
            return
        ascii_bgr = self.ascii_engine.convert_frame_to_image(frame)
        h, w, ch = frame.shape
        fps = self.media_handler.fps
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        temp_video_path = os.path.join(tempfile.gettempdir(), "ascii_temp_export.mp4")
        out = cv2.VideoWriter(temp_video_path, fourcc, fps, (w, h))
        self.media_handler.reset()
        total = self.media_handler.total_frames
        for i in range(total):
            ret, frame = self.media_handler.get_next_frame()
            if not ret:
                break
            ascii_bgr = self.ascii_engine.convert_frame_to_image(frame)
            if ascii_bgr is not None:
                if ascii_bgr.shape[:2] != (h, w):
                    ascii_bgr = cv2.resize(ascii_bgr, (w, h), interpolation=cv2.INTER_AREA)
                out.write(ascii_bgr)
            if i % 10 == 0:
                self.video_display.set_text(f"Exporting... {i}/{total} frames")
                QApplication.processEvents()
        out.release()
        if self.media_handler.has_audio and not self.cb_mute.isChecked():
            self.video_display.set_text("Muxing audio... please wait.")
            QApplication.processEvents()
            try:
                video_clip = VideoFileClip(temp_video_path)
                audio_clip = AudioFileClip(self.media_handler.audio_path)
                final_clip = video_clip.set_audio(audio_clip)
                final_clip.write_videofile(save_path, codec="libx264", audio_codec="aac", logger=None)
                video_clip.close()
                audio_clip.close()
                final_clip.close()
                os.remove(temp_video_path)
            except Exception as e:
                print(f"Error muxing audio: {e}")
                import shutil
                shutil.copy(temp_video_path, save_path)
        else:
            import shutil
            shutil.copy(temp_video_path, save_path)
            os.remove(temp_video_path)
        self.media_handler.reset()
        self.video_display.set_text("Export complete!")
        QMessageBox.information(self, "Success", "Video exported successfully!")
    def closeEvent(self, event):
        self.stop_video()
        self.media_handler.release()
        event.accept()
if __name__ == "__main__":
    app = QApplication(sys.argv)
    qdarktheme.setup_theme() if hasattr(qdarktheme, 'setup_theme') else app.setStyleSheet(qdarktheme.load_stylesheet())
    window = AsciiApp()
    window.show()
    sys.exit(app.exec())
