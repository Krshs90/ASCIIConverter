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
                             QMessageBox, QSlider, QStyle, QCheckBox, QDoubleSpinBox)
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
        self.playback_start_time = 0
        self.playback_start_frame = 0
    def run(self):
        target_delay = 1.0 / self.media_handler.fps if self.media_handler.fps > 0 else 0.033
        self.playback_start_time = time.time()
        self.playback_start_frame = self.media_handler.current_frame_idx
        while self._run_flag:
            loop_start = time.time()
            if self.seek_request is not None:
                self.media_handler.set_frame_position(self.seek_request)
                self.playback_start_time = loop_start
                self.playback_start_frame = self.seek_request
                self.seek_request = None
            if not self.is_paused:
                if self.media_handler.is_video:
                    elapsed = time.time() - self.playback_start_time
                    target_frame_idx = self.playback_start_frame + int(elapsed * self.media_handler.fps)
                    if self.media_handler.current_frame_idx < target_frame_idx - 1:
                        ret, frame = self.media_handler.get_next_frame()
                        if ret:
                            self.progress_signal.emit(self.media_handler.current_frame_idx)
                        continue
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
                    now = time.time()
                    expected_time_for_next_frame = self.playback_start_time + ((self.media_handler.current_frame_idx - self.playback_start_frame) / self.media_handler.fps)
                    sleep_time = expected_time_for_next_frame - now
                    if sleep_time > 0:
                        self.msleep(int(sleep_time * 1000))
                    else:
                        self.msleep(1)
                else:
                    if self.is_looping and self.media_handler.is_video:
                        self.media_handler.reset()
                        self.playback_start_time = time.time()
                        self.playback_start_frame = 0
                        continue
                    self.playback_finished_signal.emit()
                    self._run_flag = False
                    break
            else:
                self.msleep(50)
                self.playback_start_time += (time.time() - loop_start)
    def stop(self):
        self._run_flag = False
        self.wait()
class YoutubeFetchThread(QThread):
    finished_signal = pyqtSignal(bool, str)
    progress_signal = pyqtSignal(str)
    def __init__(self, media_handler, url):
        super().__init__()
        self.media_handler = media_handler
        self.url = url
    def run(self):
        try:
            if self.media_handler.load_media(self.url, is_youtube=True, progress_callback=self.progress_signal.emit):
                self.finished_signal.emit(True, "")
            else:
                self.finished_signal.emit(False, "Could not fetch YouTube stream.")
        except Exception as e:
            self.finished_signal.emit(False, str(e))
class AsciiApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ASCII Art Converter V1.5.0")
        self.resize(1100, 800)
        self.ascii_engine = AsciiEngine()
        self.media_handler = MediaHandler()
        self.video_thread = None
        self.is_scrubbing = False
        self._last_rendered_frame = None
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
        self.btn_clear_media = QPushButton("Clear Media")
        self.btn_clear_media.clicked.connect(self.clear_media)
        load_layout.addWidget(self.btn_clear_media)
        load_group.setLayout(load_layout)
        left_panel.addWidget(load_group)
        settings_group = QGroupBox("Appearance Settings")
        settings_layout = QVBoxLayout()
        self.cb_realism = QCheckBox("Realism Mode")
        self.cb_realism.setToolTip(
            "Automatically configures all settings for maximum visual fidelity.\n"
            "Uses detailed charset, high resolution, small font, and\n"
            "advanced color compensation to look as close to the\n"
            "original as possible — without lagging your computer."
        )
        self.cb_realism.stateChanged.connect(self.toggle_realism)
        settings_layout.addWidget(self.cb_realism)
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
        self.spin_detail = QSpinBox()
        self.spin_detail.setRange(20, 500)
        self.spin_detail.setValue(100)
        self.spin_detail.setKeyboardTracking(False)
        self.spin_detail.valueChanged.connect(self.change_detail)
        detail_layout.addStretch()
        detail_layout.addWidget(self.spin_detail)
        settings_layout.addLayout(detail_layout)
        self.slider_detail = QSlider(Qt.Orientation.Horizontal)
        self.slider_detail.setRange(20, 500)
        self.slider_detail.setValue(100)
        self.slider_detail.valueChanged.connect(self.spin_detail.setValue)
        self.spin_detail.valueChanged.connect(self.slider_detail.setValue)
        settings_layout.addWidget(self.slider_detail)
        bright_layout = QHBoxLayout()
        bright_layout.addWidget(QLabel("Brightness Boost:"))
        self.spin_bright = QDoubleSpinBox()
        self.spin_bright.setRange(1.0, 5.0)
        self.spin_bright.setSingleStep(0.1)
        self.spin_bright.setValue(1.0)
        self.spin_bright.setKeyboardTracking(False)
        self.spin_bright.valueChanged.connect(self.change_brightness)
        bright_layout.addStretch()
        bright_layout.addWidget(self.spin_bright)
        settings_layout.addLayout(bright_layout)
        self.slider_bright = QSlider(Qt.Orientation.Horizontal)
        self.slider_bright.setRange(10, 50)
        self.slider_bright.setValue(10)
        self.slider_bright.valueChanged.connect(lambda v: self.spin_bright.setValue(v / 10.0))
        self.spin_bright.valueChanged.connect(lambda v: self.slider_bright.setValue(int(v * 10)))
        settings_layout.addWidget(self.slider_bright)
        self.cb_true_color = QCheckBox("True Color Compensation")
        self.cb_true_color.setToolTip(
            "Uses perceptual LAB color space to compensate for the darkness\n"
            "of ASCII character gaps, preserving original brightness and\n"
            "accurate hue/saturation."
        )
        self.cb_true_color.stateChanged.connect(self.toggle_true_color)
        settings_layout.addWidget(self.cb_true_color)
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
        export_group = QGroupBox("Export")
        export_layout = QVBoxLayout()
        export_layout.addWidget(QLabel("Compression:"))
        self.cb_compress = QComboBox()
        self.cb_compress.addItems(["No Compression", "Discord/Slack (<20MB)"])
        export_layout.addWidget(self.cb_compress)
        quality_layout = QHBoxLayout()
        quality_layout.addWidget(QLabel("JPG Quality:"))
        self.slider_jpg_quality = QSlider(Qt.Orientation.Horizontal)
        self.slider_jpg_quality.setRange(1, 100)
        self.slider_jpg_quality.setValue(95)
        self.lbl_jpg_quality = QLabel("95")
        self.slider_jpg_quality.valueChanged.connect(
            lambda v: self.lbl_jpg_quality.setText(str(v))
        )
        quality_layout.addWidget(self.slider_jpg_quality)
        quality_layout.addWidget(self.lbl_jpg_quality)
        export_layout.addLayout(quality_layout)
        self.slider_jpg_quality.setVisible(False)
        self.lbl_jpg_quality.setVisible(False)
        self._jpg_quality_label = quality_layout.itemAt(0).widget()
        self._jpg_quality_label.setVisible(False)
        self.btn_export = QPushButton("Export Video (MP4/MOV)")
        self.btn_export.clicked.connect(self.export_media)
        export_layout.addWidget(self.btn_export)
        export_group.setLayout(export_layout)
        left_panel.addWidget(export_group)
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
                self._update_export_ui()
                self.setup_playback()
            else:
                QMessageBox.critical(self, "Error", "Could not load media file.")
    def load_youtube(self):
        url = self.txt_yt_url.text().strip()
        if url:
            import urllib.parse
            parsed = urllib.parse.urlparse(url)
            if not (parsed.scheme in ['http', 'https'] and ('youtube.com' in parsed.netloc or 'youtu.be' in parsed.netloc)):
                QMessageBox.warning(self, "Invalid URL", "Please enter a valid YouTube URL (e.g. https://youtube.com/... or https://youtu.be/...).")
                return
            self.stop_video()
            self.btn_load_yt.setEnabled(False)
            self.txt_yt_url.setEnabled(False)
            self.video_display.set_text("Fetching YouTube stream... please wait.")
            self.yt_fetch_thread = YoutubeFetchThread(self.media_handler, url)
            self.yt_fetch_thread.progress_signal.connect(self.video_display.set_text)
            self.yt_fetch_thread.finished_signal.connect(self.on_youtube_fetched)
            self.yt_fetch_thread.start()
    def on_youtube_fetched(self, success, error_msg):
        self.btn_load_yt.setEnabled(True)
        self.txt_yt_url.setEnabled(True)
        if success:
            self._update_export_ui()
            self.setup_playback()
        else:
            QMessageBox.critical(self, "Error", f"Failed to load YouTube video:\n\n{error_msg}")
            self.video_display.set_text("Load media to begin.")
    def setup_playback(self):
        if self.media_handler.is_video:
            self.slider_progress.setEnabled(True)
            self.slider_progress.setRange(0, self.media_handler.total_frames)
        else:
            self.slider_progress.setEnabled(False)
            self.lbl_time.setText("--:-- / --:--")
        self.play_video()
    def clear_media(self):
        self.stop_video()
        self.media_handler.release()
        self._last_rendered_frame = None
        self.video_display.set_text("Load media to begin.")
        self.slider_progress.setEnabled(False)
        self.lbl_time.setText("00:00 / 00:00")
        self._update_export_ui()
    def _update_export_ui(self):
        is_image = (not self.media_handler.is_video and hasattr(self.media_handler, 'single_image'))
        if is_image:
            self.btn_export.setText("Export Image (PNG/JPG)")
            self.slider_jpg_quality.setVisible(True)
            self.lbl_jpg_quality.setVisible(True)
            self._jpg_quality_label.setVisible(True)
        else:
            self.btn_export.setText("Export Video (MP4/MOV)")
            self.slider_jpg_quality.setVisible(False)
            self.lbl_jpg_quality.setVisible(False)
            self._jpg_quality_label.setVisible(False)
    def reset_settings(self):
        self.cb_realism.setChecked(False)
        self.cb_charset.setCurrentText("Standard")
        self.cb_colormode.setCurrentText("Original")
        self.spin_detail.setValue(100)
        self.spin_bright.setValue(1.0)
        self.cb_loop.setChecked(False)
        self.sb_font.setValue(12)
        self.cb_true_color.setChecked(False)
    def toggle_realism(self, state):
        is_on = (state == 2)
        if is_on:
            self.ascii_engine.apply_realism()
            self._sync_ui_to_engine()
            self._set_appearance_controls_enabled(False)
        else:
            self.ascii_engine.restore_from_realism()
            self._sync_ui_to_engine()
            self._set_appearance_controls_enabled(True)
        self.refresh_image()
    def _sync_ui_to_engine(self):
        for widget in [self.cb_charset, self.cb_colormode, self.spin_detail,
                       self.slider_detail, self.spin_bright, self.slider_bright,
                       self.sb_font, self.cb_true_color]:
            widget.blockSignals(True)
        self.cb_charset.setCurrentText(self.ascii_engine.current_char_set)
        self.cb_colormode.setCurrentText(self.ascii_engine.color_mode)
        self.spin_detail.setValue(self.ascii_engine.output_width)
        self.slider_detail.setValue(self.ascii_engine.output_width)
        self.spin_bright.setValue(self.ascii_engine.brightness_boost)
        self.slider_bright.setValue(int(self.ascii_engine.brightness_boost * 10))
        font_size = self.ascii_engine.font.size if hasattr(self.ascii_engine.font, 'size') else 12
        self.sb_font.setValue(font_size)
        self.cb_true_color.setChecked(self.ascii_engine.true_color_compensation)
        for widget in [self.cb_charset, self.cb_colormode, self.spin_detail,
                       self.slider_detail, self.spin_bright, self.slider_bright,
                       self.sb_font, self.cb_true_color]:
            widget.blockSignals(False)
    def _set_appearance_controls_enabled(self, enabled):
        self.cb_charset.setEnabled(enabled)
        self.cb_colormode.setEnabled(enabled)
        self.btn_custom_color.setEnabled(enabled and self.cb_colormode.currentText() == "Custom")
        self.spin_detail.setEnabled(enabled)
        self.slider_detail.setEnabled(enabled)
        self.spin_bright.setEnabled(enabled)
        self.slider_bright.setEnabled(enabled)
        self.cb_true_color.setEnabled(enabled)
        self.sb_font.setEnabled(enabled)
    def toggle_true_color(self, state):
        is_on = (state == 2)
        self.ascii_engine.true_color_compensation = is_on
        self.refresh_image()
    def toggle_mute(self, state):
        if state == 2:
            pygame.mixer.music.set_volume(0.0)
        else:
            pygame.mixer.music.set_volume(1.0)
    def change_charset(self, text):
        self.ascii_engine.set_char_set(text)
        self.refresh_image()
    def change_colormode(self, text):
        self.ascii_engine.color_mode = text
        self.btn_custom_color.setEnabled(text == "Custom")
        self.refresh_image()
    def pick_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.ascii_engine.custom_color = (color.red(), color.green(), color.blue())
            self.refresh_image()
    def change_detail(self, val):
        self.ascii_engine.output_width = val
        if val > 300 and not getattr(self, '_warned_detail', False):
            self._warned_detail = True
            QMessageBox.warning(self, "High Detail Warning", "Details above 300 may cause the application to lag, use excessive memory, or crash! Proceed with caution.")
        self.refresh_image()
    def change_brightness(self, val):
        self.ascii_engine.brightness_boost = val
        self.refresh_image()
    def change_font_size(self, val):
        self.ascii_engine.set_font_size(val)
        self.refresh_image()
    def refresh_image(self):
        if self.media_handler.is_video:
            return
        if not hasattr(self.media_handler, 'single_image') or self.media_handler.single_image is None:
            return
        frame = self.media_handler.single_image
        ascii_bgr = self.ascii_engine.convert_frame_to_image(frame)
        if ascii_bgr is not None:
            self._last_rendered_frame = ascii_bgr
            rgb_image = cv2.cvtColor(ascii_bgr, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w
            qt_format = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            self.video_display.set_image(qt_format.copy())
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
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass
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
    def export_media(self):
        is_image = (not self.media_handler.is_video and hasattr(self.media_handler, 'single_image') and self.media_handler.single_image is not None)
        if is_image:
            self.export_image()
        else:
            self.export_video()
    def export_image(self):
        save_path, selected_filter = QFileDialog.getSaveFileName(
            self, "Save Image", "",
            "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg)"
        )
        if not save_path:
            return
        frame = self.media_handler.single_image
        ascii_bgr = self.ascii_engine.convert_frame_to_image(frame)
        if ascii_bgr is None:
            QMessageBox.critical(self, "Error", "Failed to render image.")
            return
        ext = os.path.splitext(save_path)[1].lower()
        if not ext:
            if "PNG" in selected_filter:
                ext = ".png"
            else:
                ext = ".jpg"
            save_path += ext
        compress_mode = self.cb_compress.currentText()
        if ext in [".jpg", ".jpeg"]:
            quality = self.slider_jpg_quality.value()
            if compress_mode == "Discord/Slack (<20MB)":
                quality = min(quality, 85)
            cv2.imwrite(save_path, ascii_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
        else:
            compression = 3
            if compress_mode == "Discord/Slack (<20MB)":
                compression = 9
            cv2.imwrite(save_path, ascii_bgr, [cv2.IMWRITE_PNG_COMPRESSION, compression])
        QMessageBox.information(self, "Success", f"Image exported successfully!\n\nSaved to: {save_path}")
    def export_video(self):
        if not self.media_handler.is_video:
            QMessageBox.information(self, "Info", "Load a video first to export.")
            return
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Video", "", "Video Files (*.mp4 *.mov);;MP4 Video (*.mp4);;QuickTime Movie (*.mov)")
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
        ext = os.path.splitext(save_path)[1].lower()
        if not ext:
            ext = ".mp4"
            save_path += ext
        temp_video_path = os.path.join(tempfile.gettempdir(), f"ascii_temp_export{ext}")
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
        compress_mode = self.cb_compress.currentText()
        if self.media_handler.has_audio and not self.cb_mute.isChecked():
            self.video_display.set_text("Muxing audio... please wait.")
            QApplication.processEvents()
            try:
                video_clip = VideoFileClip(temp_video_path)
                audio_clip = AudioFileClip(self.media_handler.audio_path)
                final_clip = video_clip.with_audio(audio_clip)
                if compress_mode == "Discord/Slack (<20MB)":
                    duration = video_clip.duration if video_clip.duration else (self.media_handler.total_frames / fps)
                    target_size_bits = 19 * 1024 * 1024 * 8
                    video_bitrate = max(100000, (target_size_bits / duration) - 128000)
                    final_clip.write_videofile(save_path, codec="libx264", audio_codec="aac", bitrate=f"{int(video_bitrate)}", preset="medium", logger=None)
                else:
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
            if compress_mode == "Discord/Slack (<20MB)":
                self.video_display.set_text("Compressing video... please wait.")
                QApplication.processEvents()
                try:
                    video_clip = VideoFileClip(temp_video_path)
                    duration = video_clip.duration if video_clip.duration else (self.media_handler.total_frames / fps)
                    target_size_bits = 19 * 1024 * 1024 * 8
                    video_bitrate = max(100000, (target_size_bits / duration))
                    video_clip.write_videofile(save_path, codec="libx264", bitrate=f"{int(video_bitrate)}", preset="medium", logger=None)
                    video_clip.close()
                    os.remove(temp_video_path)
                except Exception as e:
                    print(f"Error compressing: {e}")
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
