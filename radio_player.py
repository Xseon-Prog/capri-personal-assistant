"""CAPRI_NIGHT_CITY_RADIO_V1_8
Локальное Радио Найт-Сити для персональной версии Капри.

Музыкальные файлы хранятся вне репозитория в Music/Capri/Night City Radio.
Видео в шапке окна беззвучное и зацикленное; звук воспроизводится только из треков.
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, QUrl, QSize
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

SUPPORTED_AUDIO = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}


class NightCityRadioWindow(QWidget):
    """Самостоятельное окно локального радио с перемешанным плейлистом."""

    def __init__(
        self,
        volume: int = 70,
        volume_changed: Optional[Callable[[int], None]] = None,
        music_dir: Optional[str | Path] = None,
        video_path: Optional[str | Path] = None,
        window_icon: Optional[QIcon] = None,
    ):
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle("NIGHT CITY RADIO // CAPRI")
        self.setMinimumSize(680, 650)
        self.resize(820, 760)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self.music_dir = Path(music_dir) if music_dir else (
            Path.home() / "Music" / "Capri" / "Night City Radio"
        )
        self.music_dir.mkdir(parents=True, exist_ok=True)
        self.video_path = Path(video_path) if video_path else (
            Path(__file__).resolve().parent / "media" / "night_city_radio.mp4"
        )
        self.icon_dir = Path(__file__).resolve().parent / "media" / "radio_icons"
        # CAPRI_RADIO_REUSE_APP_ICON_V1_8: reuse the same icon as Capri's tray/application.
        if window_icon is not None:
            self.setWindowIcon(window_icon)
        self._volume_changed = volume_changed
        self._tracks: list[Path] = []
        self._deck: list[Path] = []
        self._history: list[Path] = []
        self._current: Optional[Path] = None
        self._duration_ms = 0
        self._seeking = False
        self._video_started = False

        self._build_ui()
        self._setup_video()
        self._setup_audio()
        self._apply_windows_titlebar_theme()  # CAPRI_RADIO_UI_V1_2
        self.refresh_library(autoplay=False)
        self._set_volume(volume, notify=False)

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QWidget {
                background: #090611;
                color: #f7eaf1;
                font-family: 'Segoe UI';
                font-size: 10pt;
            }
            QFrame#radioCard {
                background: #100b19;
                border: 1px solid #ff2868;
                border-radius: 12px;
            }
            QLabel#eyebrow {
                color: #28ff96;
                font-family: Consolas;
                font-weight: bold;
                letter-spacing: 2px;
            }
            QLabel#stationTitle {
                color: #ff3b78;
                font-size: 22pt;
                font-weight: 800;
                letter-spacing: 2px;
            }
            QLabel#trackTitle {
                color: #fff0f6;
                font-size: 17pt;
                font-weight: 700;
            }
            QLabel#artistLabel, QLabel#mutedText {
                color: #a99bad;
            }
            /* Прозрачный фон метаданных: текст лежит прямо на карточке без чёрных полос. */
            QFrame#radioCard QLabel#trackTitle,
            QFrame#radioCard QLabel#artistLabel {
                background: transparent;
            }
            QPushButton {
                background: #1a1021;
                border: 1px solid #7a2850;
                border-radius: 8px;
                padding: 10px 16px;
                color: #fbe8f0;
                min-height: 22px;
            }
            QPushButton:hover {
                background: #31152a;
                border-color: #ff2868;
            }
            QPushButton:pressed { background: #4a1730; }
            QPushButton#iconControl {
                background: #1a1021;
                border: 1px solid #7a2850;
                border-radius: 9px;
                padding: 6px;
                min-width: 44px;
                max-width: 44px;
                min-height: 44px;
                max-height: 44px;
            }
            QPushButton#iconControl:hover {
                background: #31152a;
                border-color: #ff2868;
            }
            QPushButton#mainControl {
                background: #ff2868;
                color: #ffffff;
                border: 1px solid #ff6f9d;
                border-radius: 10px;
                padding: 8px;
                min-width: 58px;
                max-width: 58px;
                min-height: 54px;
                max-height: 54px;
            }
            QPushButton#mainControl:hover { background: #ff4a84; }
            QPushButton#utilityButton {
                color: #28ff96;
                border-color: #176448;
            }
            QSlider::groove:horizontal {
                height: 5px;
                background: #37273c;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #28ff96;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ff2868;
                border: 1px solid #ffd3e1;
                width: 13px;
                margin: -5px 0;
                border-radius: 7px;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(13)

        heading = QHBoxLayout()
        title_col = QVBoxLayout()
        eyebrow = QLabel("CAPRI  //  LOCAL TRANSMISSION")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("NIGHT CITY RADIO")
        title.setObjectName("stationTitle")
        title_col.addWidget(eyebrow)
        title_col.addWidget(title)
        heading.addLayout(title_col)
        heading.addStretch(1)
        self.live_label = QLabel("● LOCAL")
        self.live_label.setStyleSheet("color:#28ff96; font-family:Consolas; font-weight:bold;")
        heading.addWidget(self.live_label, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(heading)

        video_card = QFrame()
        video_card.setObjectName("radioCard")
        video_layout = QVBoxLayout(video_card)
        video_layout.setContentsMargins(8, 8, 8, 8)
        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(215)
        self.video_widget.setMaximumHeight(330)
        # Заполняем весь видеоблок без чёрных полей по бокам: видео масштабируется
        # до ширины контейнера, лишнее по вертикали аккуратно обрезается.
        self.video_widget.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatioByExpanding)
        self.video_widget.setStyleSheet("background:#05030a; border-radius:8px;")
        video_layout.addWidget(self.video_widget)
        root.addWidget(video_card, stretch=1)

        track_card = QFrame()
        track_card.setObjectName("radioCard")
        track_layout = QVBoxLayout(track_card)
        track_layout.setContentsMargins(18, 15, 18, 15)
        track_layout.setSpacing(4)
        self.track_title = QLabel("Радио выключено")
        self.track_title.setObjectName("trackTitle")
        self.track_title.setWordWrap(True)
        self.artist_label = QLabel("Добавь музыку в папку Night City Radio")
        self.artist_label.setObjectName("artistLabel")
        self.artist_label.setWordWrap(True)
        track_layout.addWidget(self.track_title)
        track_layout.addWidget(self.artist_label)
        root.addWidget(track_card)

        progress_layout = QHBoxLayout()
        self.position_label = QLabel("00:00")
        self.duration_label = QLabel("00:00")
        self.position_label.setObjectName("mutedText")
        self.duration_label.setObjectName("mutedText")
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.setEnabled(False)
        self.seek_slider.sliderPressed.connect(self._begin_seek)
        self.seek_slider.sliderReleased.connect(self._finish_seek)
        progress_layout.addWidget(self.position_label)
        progress_layout.addWidget(self.seek_slider, stretch=1)
        progress_layout.addWidget(self.duration_label)
        root.addLayout(progress_layout)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.previous_button = QPushButton()
        self.previous_button.setObjectName("iconControl")
        self.previous_button.setToolTip("Предыдущая композиция")
        self._set_control_icon(self.previous_button, "previous.png", "|◀", 25)
        self.previous_button.clicked.connect(self.previous_track)

        self.play_button = QPushButton()
        self.play_button.setObjectName("mainControl")
        self.play_button.setToolTip("Воспроизвести / пауза")
        self._set_control_icon(self.play_button, "play.png", "▶", 31)
        self.play_button.clicked.connect(self.toggle_play_pause)

        self.next_button = QPushButton()
        self.next_button.setObjectName("iconControl")
        self.next_button.setToolTip("Следующая композиция")
        self._set_control_icon(self.next_button, "next.png", "▶|", 25)
        self.next_button.clicked.connect(self.next_track)

        controls.addStretch(1)
        controls.addWidget(self.previous_button)
        controls.addWidget(self.play_button)
        controls.addWidget(self.next_button)
        controls.addStretch(1)
        root.addLayout(controls)

        volume_row = QHBoxLayout()
        volume_text = QLabel("ГРОМКОСТЬ")
        volume_text.setObjectName("eyebrow")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setMaximumWidth(250)
        self.volume_value = QLabel("70%")
        self.volume_value.setObjectName("mutedText")
        volume_row.addWidget(volume_text)
        volume_row.addStretch(1)
        volume_row.addWidget(self.volume_slider)
        volume_row.addWidget(self.volume_value)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.volume_slider.sliderReleased.connect(self._persist_volume)
        root.addLayout(volume_row)

        bottom = QHBoxLayout()
        self.folder_button = QPushButton("Открыть папку с музыкой")
        self.folder_button.setObjectName("utilityButton")
        self.folder_button.clicked.connect(self.open_music_folder)
        self.refresh_button = QPushButton("Обновить библиотеку")
        self.refresh_button.setObjectName("utilityButton")
        self.refresh_button.clicked.connect(lambda: self.refresh_library(autoplay=False))
        self.close_button = QPushButton("Закрыть")
        self.close_button.setToolTip("Остановить музыку и закрыть радио")
        self.close_button.clicked.connect(self._close_radio)
        bottom.addWidget(self.folder_button)
        bottom.addWidget(self.refresh_button)
        bottom.addStretch(1)
        bottom.addWidget(self.close_button)
        root.addLayout(bottom)

        path_label = QLabel(str(self.music_dir))
        path_label.setObjectName("mutedText")
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_label.setWordWrap(True)
        root.addWidget(path_label)

    def _set_control_icon(self, button: QPushButton, filename: str, fallback: str, size: int) -> None:
        """Загружает пользовательскую монохромную иконку управления радио."""
        icon_path = self.icon_dir / filename
        if icon_path.is_file():
            button.setIcon(QIcon(str(icon_path)))
            button.setIconSize(QSize(size, size))
            button.setText("")
        else:
            button.setText(fallback)

    def _update_play_icon(self, playing: bool) -> None:
        # Одна центральная кнопка показывает реальное действие: Pause во время
        # воспроизведения и Play на паузе/остановке. Отдельной кнопки Stop нет.
        if playing:
            self._set_control_icon(self.play_button, "pause.png", "Ⅱ", 31)
            self.play_button.setToolTip("Пауза")
        else:
            self._set_control_icon(self.play_button, "play.png", "▶", 31)
            self.play_button.setToolTip("Воспроизвести")

    def _apply_windows_titlebar_theme(self) -> None:
        """Оформляет системную строку заголовка Windows в палитре Капри.

        Оставляем штатную рамку Windows: так сохраняются перетаскивание,
        изменение размера, сворачивание и системная кнопка закрытия.
        На версиях Windows без поддержки цветовой настройки останется штатная
        системная строка, само окно и все кнопки приложения продолжат работать.
        """
        import sys
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = ctypes.c_void_p(int(self.winId()))
            dwmapi = ctypes.WinDLL("dwmapi")

            def set_attribute(attribute: int, value: int) -> int:
                data = ctypes.c_int(value)
                return int(dwmapi.DwmSetWindowAttribute(
                    hwnd, ctypes.c_uint(attribute), ctypes.byref(data), ctypes.sizeof(data)
                ))

            # DWMWA_USE_IMMERSIVE_DARK_MODE: 20 (актуальная), 19 (старые сборки Win10).
            result = set_attribute(20, 1)
            if result != 0:
                set_attribute(19, 1)
            # COLORREF хранится в формате 0x00BBGGRR.
            set_attribute(35, 0x00110609)  # DWMWA_CAPTION_COLOR: #090611
            set_attribute(36, 0x00F1EAF7)  # DWMWA_TEXT_COLOR: #F7EAF1
            set_attribute(34, 0x006828FF)  # DWMWA_BORDER_COLOR: #FF2868
        except Exception:
            # Стилизация title bar необязательна и не должна мешать запуску радио.
            pass

    def _setup_video(self) -> None:
        self.video_player = QMediaPlayer(self)
        self.video_audio = QAudioOutput(self)
        self.video_audio.setMuted(True)
        self.video_player.setAudioOutput(self.video_audio)
        self.video_player.setVideoOutput(self.video_widget)
        self.video_player.mediaStatusChanged.connect(self._video_status_changed)
        self.video_player.errorOccurred.connect(self._video_error)
        if self.video_path.is_file():
            self.video_player.setSource(QUrl.fromLocalFile(str(self.video_path.resolve())))
            self.video_player.setLoops(QMediaPlayer.Loops.Infinite)
        else:
            self.live_label.setText("● AUDIO ONLY")

    def _setup_audio(self) -> None:
        self.audio_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_player.setAudioOutput(self.audio_output)
        self.audio_player.positionChanged.connect(self._position_changed)
        self.audio_player.durationChanged.connect(self._duration_changed)
        self.audio_player.playbackStateChanged.connect(self._playback_state_changed)
        self.audio_player.mediaStatusChanged.connect(self._media_status_changed)
        self.audio_player.errorOccurred.connect(self._audio_error)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        if self.video_path.is_file():
            self.video_player.play()
            self._video_started = True

    def _video_status_changed(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.video_player.setPosition(0)
            self.video_player.play()

    def _video_error(self, error, message="") -> None:
        if error != QMediaPlayer.Error.NoError:
            self.live_label.setText("● VIDEO OFFLINE")

    def refresh_library(self, autoplay: bool = False) -> None:
        old_current = self._current
        self._tracks = sorted(
            (p for p in self.music_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO),
            key=lambda p: str(p).casefold(),
        )
        self._deck = [p for p in self._tracks if p != old_current]
        random.shuffle(self._deck)
        if old_current in self._tracks:
            self._current = old_current
        else:
            self._current = None
        count = len(self._tracks)
        self.live_label.setText(f"● {count} TRACKS")
        if not count:
            self.track_title.setText("Библиотека пока пуста")
            self.artist_label.setText("Добавь MP3, WAV, FLAC, OGG, M4A или другие поддерживаемые файлы.")
            self._update_play_icon(False)
        elif self._current is None:
            self.track_title.setText("NIGHT CITY RADIO готово")
            self.artist_label.setText("Нажми ▶, чтобы начать случайное воспроизведение.")
        if autoplay and count:
            self.next_track()

    def _refill_deck(self) -> None:
        self._deck = list(self._tracks)
        random.shuffle(self._deck)
        if len(self._deck) > 1 and self._current == self._deck[0]:
            self._deck[0], self._deck[1] = self._deck[1], self._deck[0]

    def _next_track(self, remember: bool = True) -> None:
        if not self._tracks:
            self.refresh_library(autoplay=False)
        if not self._tracks:
            self.artist_label.setText("Добавь музыку в папку Night City Radio.")
            self.live_label.setText("● EMPTY")
            return
        if not self._deck:
            self._refill_deck()
        if not self._deck:
            return
        if remember and self._current is not None:
            self._history.append(self._current)
            self._history = self._history[-300:]
        path = self._deck.pop(0)
        self._load_and_play(path)

    def next_track(self) -> None:
        self._next_track(remember=True)

    def previous_track(self) -> None:
        if self._current is None:
            self.next_track()
            return
        if self.audio_player.position() > 5000 or not self._history:
            self.audio_player.setPosition(0)
            self.audio_player.play()
            return
        self._deck.insert(0, self._current)
        previous = self._history.pop()
        self._load_and_play(previous)

    def _load_and_play(self, path: Path) -> None:
        self._current = path
        if " - " in path.stem:
            artist, title = path.stem.split(" - ", 1)
            self.track_title.setText(title.strip())
            self.artist_label.setText(artist.strip())
        else:
            self.track_title.setText(path.stem)
            self.artist_label.setText("ЛОКАЛЬНЫЙ ТРЕК · NIGHT CITY RADIO")
        self.live_label.setText("● LOADING")
        self.position_label.setText("00:00")
        self.duration_label.setText("00:00")
        self.seek_slider.setValue(0)
        self.seek_slider.setEnabled(False)
        self.audio_player.stop()
        self.audio_player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        self.audio_player.play()

    def toggle_play_pause(self) -> None:
        state = self.audio_player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.audio_player.pause()
        elif self._current is not None:
            self.audio_player.play()
        else:
            self.next_track()

    def stop_radio(self) -> None:
        self.audio_player.stop()
        self._current = None
        self._history.clear()
        self.position_label.setText("00:00")
        self.duration_label.setText("00:00")
        self.seek_slider.setValue(0)
        self.track_title.setText("Воспроизведение остановлено")
        self.artist_label.setText("Нажми Play, чтобы включить следующую композицию.")
        self.live_label.setText("● STOPPED")
        self._update_play_icon(False)

    def open_music_folder(self) -> None:
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.music_dir.resolve())))

    def _on_volume_changed(self, value: int) -> None:
        # Громкость применяется сразу; config.json записываем один раз после отпускания слайдера.
        self._set_volume(value, notify=False)

    def _persist_volume(self) -> None:
        if self._volume_changed:
            self._volume_changed(self.volume_slider.value())

    def _set_volume(self, value: int, notify: bool) -> None:
        value = max(0, min(100, int(value)))
        self.audio_output.setVolume(value / 100.0)
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(value)
        self.volume_slider.blockSignals(False)
        self.volume_value.setText(f"{value}%")
        if notify and self._volume_changed:
            self._volume_changed(value)

    def _begin_seek(self) -> None:
        self._seeking = True

    def _finish_seek(self) -> None:
        if self._duration_ms > 0:
            position = int(self.seek_slider.value() * self._duration_ms / 1000)
            self.audio_player.setPosition(position)
        self._seeking = False

    def _position_changed(self, position: int) -> None:
        self.position_label.setText(self._format_time(position))
        if not self._seeking and self._duration_ms > 0:
            self.seek_slider.setValue(int(position * 1000 / self._duration_ms))

    def _duration_changed(self, duration: int) -> None:
        self._duration_ms = max(0, int(duration))
        self.duration_label.setText(self._format_time(duration))
        self.seek_slider.setEnabled(duration > 0)

    def _playback_state_changed(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._update_play_icon(playing)
        if playing:
            self.live_label.setText("● ON AIR")
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.live_label.setText("● PAUSED")
        else:
            self.live_label.setText("● LOCAL")

    def _media_status_changed(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._next_track(remember=True)

    def _audio_error(self, error, message="") -> None:
        if error != QMediaPlayer.Error.NoError:
            self.live_label.setText("● AUDIO ERROR")
            self.artist_label.setText("Не удалось воспроизвести файл. Проверь его формат.")

    @staticmethod
    def _format_time(milliseconds: int) -> str:
        seconds = max(0, int(milliseconds) // 1000)
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _stop_playback(self) -> None:
        """Останавливает аудио и видео, очищает текущую позицию; безопасно вызывать повторно."""
        self.audio_player.stop()
        self.video_player.stop()
        self._video_started = False
        self._current = None
        self._history.clear()
        self.position_label.setText("00:00")
        self._duration_ms = 0
        self.duration_label.setText("00:00")
        self.seek_slider.setValue(0)
        self.seek_slider.setEnabled(False)
        self.track_title.setText("Радио закрыто")
        self.artist_label.setText("Открой радио, чтобы начать воспроизведение снова.")
        self.live_label.setText("● LOCAL")
        self._update_play_icon(False)

    def _close_radio(self) -> None:
        """Кнопка «Закрыть»: сначала останавливает оба проигрывателя, затем закрывает окно."""
        self._stop_playback()
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        # Системный крестик также всегда останавливает музыку и видео.
        self._stop_playback()
        event.accept()
