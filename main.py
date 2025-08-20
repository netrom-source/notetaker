# Notator - en minimalistisk skrivemaskine
# ---------------------------------------
# Denne kode implementerer et simpelt skriveprogram i PyQt6.
# Programmet er designet til at køre på en Raspberry Pi 3a+
# og er derfor holdt så letvægts som muligt.
# Hver del af koden er grundigt kommenteret på dansk
# for at hjælpe både AI og mennesker med at forstå logikken.

import sys
import os
import time
import json
from glob import glob
from PyQt6 import QtWidgets, QtCore, QtGui
from smbus2 import SMBus

# Rodmappen til programmet bruges til at finde resourcer som ikoner.
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Sti til hvor noter gemmes. Altid i ``~/data`` så det er let at finde
# filerne uafhængigt af hvor programmet ligger.
DATA_DIR = os.path.join(os.path.expanduser("~"), "data")
# Session-information lægges samme sted så den genskabes korrekt.
SESSION_FILE = os.path.join(DATA_DIR, "session.json")

# Hjælpefunktion til at vælge en monospace-font.
# Programmet forsøger JetBrains Mono først og falder
# tilbage til Noto Sans Mono eller Iosevka hvis de ikke
# findes på systemet. Dermed sikres ensartet udseende
# selv på minimalistiske installationer som Raspberry Pi.
def pick_mono_font() -> str:
    """Returner navnet på en tilgængelig monospace-font.

    QFontDatabase i Qt6 benytter statiske metoder og kræver at der er
    oprettet en QApplication inden den kan benyttes. Vi antager derfor at
    funktionen først kaldes efter ``QApplication`` er initialiseret.
    """
    families = QtGui.QFontDatabase.families()
    for name in ["JetBrains Mono", "Noto Sans Mono", "Iosevka"]:
        if name in families:
            return name
    return QtGui.QFont().defaultFamily()

# ----- UPS HAT overvågning -----

class UPSMonitor:
    """Læser batterioplysninger fra Waveshare UPS HAT (E) via I2C.

    Registrene er beskrevet i Waveshares dokumentation. Her anvendes
    kun de mest relevante: batteriprocent, opladningsstatus samt
    estimerede tider for af- og opladning i minutter. Alle adresser er
    forudsat på I2C-adressen ``0x2d``.
    """

    ADDRESS = 0x2D
    REG_PERCENT_L = 0x24
    REG_PERCENT_H = 0x25
    REG_TIME_L = 0x28  # resterende afladningstid i minutter
    REG_TIME_H = 0x29
    REG_CHARGE_TIME_L = 0x2A  # resterende opladningstid i minutter
    REG_CHARGE_TIME_H = 0x2B
    REG_CHARGE_STATE = 0x02

    def __init__(self, bus: int = 1) -> None:
        self.bus_num = bus
        try:
            self.bus = SMBus(bus)
        except FileNotFoundError:
            # I2C er ikke aktiveret eller findes ikke
            self.bus = None

    def _read_word(self, reg_l: int, reg_h: int) -> int:
        """Læs to registre og kombiner til et 16-bit tal."""
        if not self.bus:
            raise OSError("Ingen I2C bus")
        low = self.bus.read_byte_data(self.ADDRESS, reg_l)
        high = self.bus.read_byte_data(self.ADDRESS, reg_h)
        return (high << 8) | low

    def _read_byte(self, reg: int) -> int:
        """Læs et enkelt register."""
        if not self.bus:
            raise OSError("Ingen I2C bus")
        return self.bus.read_byte_data(self.ADDRESS, reg)

    def status(
        self,
    ) -> tuple[int | None, int | None, int | None, bool | None]:
        """Returner batteriprocent, afladnings- og opladningstid.

        Hvis der opstår en fejl returneres ``(None, None, None, None)``.
        """

        try:
            pct = self._read_word(self.REG_PERCENT_L, self.REG_PERCENT_H)
            dis_mins = self._read_word(self.REG_TIME_L, self.REG_TIME_H)
            chg_mins = self._read_word(
                self.REG_CHARGE_TIME_L, self.REG_CHARGE_TIME_H
            )
            state = self._read_byte(self.REG_CHARGE_STATE)
            charging = bool(state & 0x80)
        except OSError:
            return None, None, None, None
        return pct, dis_mins, chg_mins, charging

# Fremhæv Markdown under skrivning
class MarkdownHighlighter(QtGui.QSyntaxHighlighter):
    """En simpel highlighter der viser Markdown-formatering direkte.

    Overskrifter (#, ## osv.) gives automatisk større skriftstørrelse,
    så man kan se hierarkiet uden et separat preview-vindue.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bold_format = QtGui.QTextCharFormat()
        self.bold_format.setFontWeight(QtGui.QFont.Weight.Bold)

        self.italic_format = QtGui.QTextCharFormat()
        self.italic_format.setFontItalic(True)

        self.heading_format = QtGui.QTextCharFormat()
        self.heading_format.setFontWeight(QtGui.QFont.Weight.Bold)
        self.heading_format.setForeground(QtGui.QBrush(QtGui.QColor("#e0e0e0")))

        # Markdown-symboler (#, *, **) tones ned i en grå farve men skal
        # beholde samme skriftstørrelse som den omkringliggende tekst.
        self.marker_format = QtGui.QTextCharFormat()
        self.marker_format.setForeground(QtGui.QColor("#666"))

        self.quote_format = QtGui.QTextCharFormat()
        self.quote_format.setForeground(QtGui.QColor("#999"))
        self.quote_format.setFontItalic(True)

        self.bullet_format = QtGui.QTextCharFormat()
        self.bullet_format.setForeground(QtGui.QColor("#bbb"))

    def highlightBlock(self, text: str) -> None:
        # **fed**
        bold = QtCore.QRegularExpression(r"\*\*(.+?)\*\*")
        it = bold.globalMatch(text)
        while it.hasNext():
            match = it.next()
            self.setFormat(match.capturedStart(1), match.capturedLength(1), self.bold_format)
            # farv selve **-markørerne svagt
            self.setFormat(match.capturedStart(), 2, self.marker_format)
            self.setFormat(match.capturedEnd() - 2, 2, self.marker_format)

        # *kursiv*
        italic = QtCore.QRegularExpression(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)")
        it = italic.globalMatch(text)
        while it.hasNext():
            match = it.next()
            self.setFormat(match.capturedStart(1), match.capturedLength(1), self.italic_format)
            self.setFormat(match.capturedStart(), 1, self.marker_format)
            self.setFormat(match.capturedEnd() - 1, 1, self.marker_format)

        # overskrifter begynder med et eller flere #
        heading = QtCore.QRegularExpression(r"^(#{1,6})\s+(.*)")
        match = heading.match(text)
        if match.hasMatch():
            level = len(match.captured(1))
            fmt = QtGui.QTextCharFormat(self.heading_format)
            base = self.document().defaultFont().pointSizeF()
            # Jo færre #, jo større skrift
            scale = {1: 2.0, 2: 1.7, 3: 1.5, 4: 1.3, 5: 1.2, 6: 1.1}.get(level, 1)
            fmt.setFontPointSize(base * scale)
            self.setFormat(0, len(text), fmt)
            # selve #-symbolerne skal følge samme størrelse og vægt, blot i grå
            marker_fmt = QtGui.QTextCharFormat(fmt)
            marker_fmt.setForeground(self.marker_format.foreground())
            self.setFormat(match.capturedStart(1), level, marker_fmt)

        bullet = QtCore.QRegularExpression(r"^\s*\*\s+(.*)")
        match = bullet.match(text)
        if match.hasMatch():
            self.setFormat(match.capturedStart(), 1, self.bullet_format)
            self.setFormat(match.capturedStart(1), len(match.captured(1)), QtGui.QTextCharFormat())

        quote = QtCore.QRegularExpression(r"^>\s+(.*)")
        match = quote.match(text)
        if match.hasMatch():
            self.setFormat(0, len(text), self.quote_format)
            self.setFormat(0, 1, self.marker_format)

# ----- Hjælpeklasser -----

class NoteTab(QtWidgets.QTextEdit):
    """En teksteditor der kan blokere sletning i Hemmingway-tilstand."""

    typed = QtCore.pyqtSignal()

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        # ``auto_name`` angiver om filnavnet er autogenereret. Når brugeren
        # gemmer med et eget navn, sættes denne til ``False`` så autosave ikke
        # skriver tilbage til den gamle sti.
        self.auto_name = True
        self.hemingway = False  # Hvis sand, blokeres sletning og navigation bagud
        # Brug den skrifttype som ``pick_mono_font`` finder. Dermed er vi
        # robuste overfor systemer hvor JetBrains Mono ikke er installeret.
        self.setFont(QtGui.QFont(pick_mono_font(), 10))
        # Mørk baggrund og små marginer i siderne samt tilpassede scrollbars
        self.default_style = (
            "background:#121212;color:#e6e6e6;"
            "QScrollBar{background:#121212;border:none;}"
            "QScrollBar::handle{background:#555;border-radius:4px;}"
            "QScrollBar::add-line,QScrollBar::sub-line{width:0;height:0;}"
            "QScrollBar::add-page,QScrollBar::sub-page{background:none;}"
        )
        self.setStyleSheet(self.default_style)
        self.margin = 24
        self.setViewportMargins(self.margin, 0, self.margin, 0)
        self.highlighter = MarkdownHighlighter(self.document())
        # Auto-gem hvert 10. sekund
        self.auto_timer = QtCore.QTimer(self)
        self.auto_timer.timeout.connect(self.auto_save)
        self.auto_timer.start(10000)

    def set_scale(self, factor: float):
        """Opdater margener efter zoom."""
        m = int(self.margin * factor)
        self.setViewportMargins(m, 0, m, 0)

    def auto_save(self):
        """Gem indholdet i filen uden notifikation."""
        if not self.file_path:
            QtWidgets.QMessageBox.warning(
                self,
                "Auto-gem fejlede",
                "Ingen filsti angivet til noten, kan ikke auto-gemme.",
            )
            return
        dirpath = os.path.dirname(self.file_path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write(self.toPlainText())

    def set_blind(self, blind: bool) -> None:
        """Skjul eller vis teksten i editoren."""
        if blind:
            style = self.default_style.replace("color:#e6e6e6", "color:#121212")
            self.setStyleSheet(style)
        else:
            self.setStyleSheet(self.default_style)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if self.hemingway:
            blocked = [
                QtCore.Qt.Key.Key_Backspace,
                QtCore.Qt.Key.Key_Delete,
                QtCore.Qt.Key.Key_Left,
                QtCore.Qt.Key.Key_Up,
            ]
            if event.key() in blocked:
                # Bloker sletning og bevægelse bagud
                return
        super().keyPressEvent(event)
        self.typed.emit()

class TimerWidget(QtWidgets.QLabel):
    """Viser en nedtælling og udsender et signal når tiden er gået.

    Denne klasse fungerer blot som et display: ``start`` sætter et
    antal sekunder og widgetten opdaterer sig selv hvert sekund via en
    intern ``QTimer``. Når nedtællingen rammer nul, udsendes ``timeout``
    så andre dele af programmet kan reagere.
    """
    timeout = QtCore.pyqtSignal()  # Signal der udsendes når tiden er gået

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        # Gem fontstørrelse og om timeren kører, så stilen kan opdateres
        # uden at miste farven ved zoom.
        self._font_size = 16
        self._running = False
        self._duration = 0
        self._remaining = 0
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._update_time)
        # Ekstra timer der får teksten til at blinke når tiden er gået
        self._blink_anim = None
        self._blinking = False
        self._text_opacity = 1.0
        self.hide()  # Timeren er skjult indtil den startes
        self._update_style()

    @QtCore.pyqtProperty(float)
    def textOpacity(self) -> float:
        return self._text_opacity

    @textOpacity.setter
    def textOpacity(self, value: float) -> None:
        self._text_opacity = value
        self._update_style()

    def start(self, seconds: int):
        """Start en nedtælling på det angivne antal sekunder."""
        # Stop eventuel blinkning fra en tidligere nedtælling
        if self._blink_anim:
            self._blink_anim.stop()
        self.setVisible(True)
        self._duration = seconds
        self._remaining = seconds
        self._blinking = False
        self._update_label()
        # Vis at timeren er aktiv med grøn baggrund
        self._running = True
        self._update_style()
        self._timer.start(1000)  # opdater hvert sekund

    def reset(self):
        """Stop og nulstil timeren."""
        self._timer.stop()
        if self._blink_anim:
            self._blink_anim.stop()
        self.hide()
        # Markér at timeren er stoppet
        self._running = False
        self._blinking = False
        self._update_style()

    def _update_time(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._finish()
        else:
            self._update_label()

    def _update_label(self):
        mins, secs = divmod(self._remaining, 60)
        self.setText(f"{mins:02d}:{secs:02d}")

    def _finish(self):
        """Kaldes når nedtællingen rammer nul."""
        self._timer.stop()
        self._running = False
        self._remaining = 0
        self._update_label()
        # Start blink-tilstand i ca. 5 sekunder (20 toggles)
        self._blinking = True
        self._update_style()
        self._start_blink()
        self.timeout.emit()

    def _start_blink(self):
        """Anvend en fade-animation for blink."""
        fade_out = QtCore.QPropertyAnimation(self, b"textOpacity")
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setDuration(125)
        fade_in = QtCore.QPropertyAnimation(self, b"textOpacity")
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setDuration(125)
        group = QtCore.QSequentialAnimationGroup(self)
        group.addAnimation(fade_out)
        group.addAnimation(fade_in)
        group.setLoopCount(20)  # ca. 5 sekunder
        group.finished.connect(self._stop_blink)
        group.start()
        self._blink_anim = group

    def _stop_blink(self):
        """Stop blink-animationen og nulstil stil."""
        self._blinking = False
        self._text_opacity = 1.0
        self._blink_anim = None
        self._update_style()
        self.hide()  # skjul timeren helt efter blink

    def update_font(self, size: int):
        """Opdater fontstørrelsen og bevar farverne."""
        self._font_size = size
        self._update_style()

    def _update_style(self):
        """Anvend stylesheet afhængigt af om timeren kører."""
        if self._blinking:
            bg = "#8b0000"  # mørk rød når tiden er gået
        elif self._running:
            bg = "#556b2f"  # støvet grøn under nedtælling
        else:
            bg = "#121212"
        color = QtGui.QColor("#e6e6e6")
        color.setAlphaF(self._text_opacity)
        self.setStyleSheet(
            f"background:{bg};color:{color.name(QtGui.QColor.NameFormat.HexArgb)};font-size:{self._font_size}pt; padding:4px;"
        )

class TimerMenu(QtWidgets.QWidget):
    """En nedfældet menu hvor brugeren vælger timerens længde.

    Menuen erstatter den tidligere dialogboks og er nu integreret som en
    skjult widget under timer-displayet. ``changed``-signalet udsendes med
    det valgte antal sekunder, hvorefter menuen skjules igen.
    """

    changed = QtCore.pyqtSignal(int)
    closed = QtCore.pyqtSignal()
    presets = [30, 3 * 60, 7 * 60, 11 * 60]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        # Kun fokusfarve defineres her -- selve knapstilen sættes globalt
        self.setStyleSheet(
            "QPushButton:focus{background:#444;}"
        )
        self.buttons = []
        for seconds in self.presets:
            btn = QtWidgets.QPushButton(self._fmt(seconds))
            btn.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
            btn.clicked.connect(lambda _, s=seconds: self._choose(s))
            btn.setAutoDefault(True)
            btn.installEventFilter(self)
            self.layout().addWidget(btn)
            self.buttons.append(btn)
        self.custom_input = QtWidgets.QLineEdit()
        self.custom_input.setPlaceholderText("Indtast tid")
        # Diskret grå kant omkring feltet
        self.custom_input.setStyleSheet(
            "QLineEdit{border:1px solid #666;background:#121212;color:#ddd;}"
        )
        self.custom_input.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.custom_input.returnPressed.connect(self._custom)
        self.custom_input.installEventFilter(self)
        self.layout().addWidget(self.custom_input)

        # Starter skjult med højde 0; animationen ændrer "maximumHeight".
        self.setMaximumHeight(0)
        self.hide()
        self.installEventFilter(self)

    def show_menu(self):
        """Vis menuen med en let slide-animation."""
        self.setVisible(True)
        self.raise_()
        if self.parent():
            self.setFixedWidth(int(self.parent().width() * 0.33))
        end = self.sizeHint().height()
        anim = QtCore.QPropertyAnimation(self, b"maximumHeight")
        anim.setStartValue(0)
        anim.setEndValue(end)
        anim.setDuration(200)
        anim.start()
        self._anim = anim
        self.buttons[0].setFocus()

    def hide_menu(self):
        """Skjul menuen igen med samme animation modsat."""
        end = self.maximumHeight()
        anim = QtCore.QPropertyAnimation(self, b"maximumHeight")
        anim.setStartValue(end)
        anim.setEndValue(0)
        anim.setDuration(200)
        anim.finished.connect(self._after_hide)
        anim.start()
        self._anim = anim

    def _after_hide(self):
        self.setVisible(False)
        self.closed.emit()

    def update_scale(self, font: QtGui.QFont, width: int):
        """Tilpas font og størrelse ved skalering."""
        self.setFont(font)
        for child in self.findChildren(QtWidgets.QWidget):
            child.setFont(font)
        if self.isVisible() and self.parent():
            parent = self.parent()
            w = int(width * 0.5)
            h = self.sizeHint().height()
            self.setFixedWidth(w)
            self.setFixedHeight(h)
            self.setGeometry((parent.width() - w) // 2, parent.height() - h, w, h)

    def update_scale(self, font: QtGui.QFont, width: int):
        self.setFont(font)
        for child in self.findChildren(QtWidgets.QWidget):
            child.setFont(font)
        if self.isVisible() and self.parent():
            w = int(width * 0.5)
            h = self.sizeHint().height()
            self.setFixedWidth(w)
            self.setFixedHeight(h)
            self.setGeometry((self.parent().width() - w) // 2, self.parent().height() - h, w, h)

    def _choose(self, seconds: int):
        self.changed.emit(seconds)
        self.custom_input.clear()
        self.hide_menu()

    def _custom(self):
        text = self.custom_input.text().strip().lower()
        try:
            if text.endswith("s"):
                seconds = int(text[:-1])
            else:
                seconds = int(text) * 60
        except ValueError:
            # Vis midlertidig advarsel direkte i feltet fremfor dialog
            self.custom_input.clear()
            old = self.custom_input.placeholderText()
            self.custom_input.setPlaceholderText("Ugyldigt input")
            QtCore.QTimer.singleShot(
                1500, lambda: self.custom_input.setPlaceholderText(old)
            )
            return
        self.changed.emit(seconds)
        self.custom_input.clear()
        self.hide_menu()

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() == QtCore.Qt.Key.Key_Escape:
                self.hide_menu()
                return True
            # Navigér mellem knapperne med piletaster
            if obj in self.buttons:
                idx = self.buttons.index(obj)
                if event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                    obj.click()
                    return True
                if event.key() in (QtCore.Qt.Key.Key_Down, QtCore.Qt.Key.Key_Right):
                    if idx == len(self.buttons) - 1:
                        self.custom_input.setFocus()
                    else:
                        self.buttons[idx + 1].setFocus()
                    return True
                if event.key() in (QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Left):
                    if idx == 0:
                        self.custom_input.setFocus()
                    else:
                        self.buttons[idx - 1].setFocus()
                    return True
            if obj is self.custom_input:
                if event.key() in (QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Left):
                    self.buttons[-1].setFocus()
                    return True
                if event.key() in (QtCore.Qt.Key.Key_Down, QtCore.Qt.Key.Key_Right):
                    self.buttons[0].setFocus()
                    return True
        return super().eventFilter(obj, event)

    def update_scale(self, font: QtGui.QFont, width: int):
        """Tilpas font og bredde efter zoom."""
        self.setFont(font)
        for child in self.findChildren(QtWidgets.QWidget):
            child.setFont(font)
        if self.isVisible() and self.parent():
            self.setFixedWidth(int(width * 0.33))
            self.setMaximumHeight(self.sizeHint().height())

    @staticmethod
    def _fmt(seconds: int) -> str:
        return f"{seconds // 60 if seconds >= 60 else seconds} {'min' if seconds >= 60 else 'sek'}"


class FileMenu(QtWidgets.QWidget):
    """En simpel menu til filnavne der glider op fra bunden."""

    accepted = QtCore.pyqtSignal(str)
    closed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background:#121212;color:#ddd;")
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.list = QtWidgets.QListWidget()
        self.layout().addWidget(self.list)
        self.line = QtWidgets.QLineEdit()
        self.layout().addWidget(self.line)
        btns = QtWidgets.QHBoxLayout()
        self.ok_btn = QtWidgets.QPushButton()
        self.ok_btn.setAutoDefault(True)
        self.ok_btn.installEventFilter(self)
        self.cancel_btn = QtWidgets.QPushButton("Annuller")
        self.cancel_btn.setAutoDefault(True)
        self.cancel_btn.installEventFilter(self)
        btns.addWidget(self.ok_btn)
        btns.addWidget(self.cancel_btn)
        self.layout().addLayout(btns)

        self.ok_btn.clicked.connect(self._emit)
        self.cancel_btn.clicked.connect(self.hide_menu)
        self.line.installEventFilter(self)
        self.list.installEventFilter(self)
        self.line.returnPressed.connect(self._emit)
        self.list.itemActivated.connect(self._emit)
        self.hide()

    def setup(self, mode: str, default: str = ""):
        """Konfigurer menuen til open eller save."""
        self.mode = mode
        self.ok_btn.setText("Åbn" if mode == "open" else "Gem")
        if mode == "open":
            self.line.hide()
            self.list.show()
            self.list.clear()
            data_dir = DATA_DIR
            try:
                files = [f[:-3] for f in os.listdir(data_dir) if f.endswith(".md")]
            except FileNotFoundError:
                files = []
            for f in files:
                self.list.addItem(f)
            if files:
                self.list.setCurrentRow(0)
            self.list.setFocus()
        else:
            self.list.hide()
            self.line.show()
            # vis standardnavn uden filendelse
            if default.endswith(".md"):
                default = os.path.splitext(default)[0]
            self.line.setText(default)
            self.line.selectAll()

    def show_menu(self):
        if not self.parent():
            return
        parent = self.parent()
        width = int(parent.width() * 0.5)
        self.setFixedWidth(width)
        h = self.sizeHint().height()
        self.setFixedHeight(h)
        start = QtCore.QRect((parent.width() - width) // 2, parent.height(), width, h)
        end = QtCore.QRect((parent.width() - width) // 2, parent.height() - h, width, h)
        self.setGeometry(start)
        self.setVisible(True)
        self.raise_()
        anim = QtCore.QPropertyAnimation(self, b"geometry")
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setDuration(200)
        anim.start()
        self._anim = anim
        if self.mode == "open":
            self.list.setFocus()
        else:
            self.line.setFocus()

    def hide_menu(self):
        if not self.parent():
            self.hide()
            return
        parent = self.parent()
        end_rect = QtCore.QRect(self.x(), parent.height(), self.width(), self.height())
        anim = QtCore.QPropertyAnimation(self, b"geometry")
        anim.setStartValue(self.geometry())
        anim.setEndValue(end_rect)
        anim.setDuration(200)
        anim.finished.connect(self._after_hide)
        anim.start()
        self._anim = anim

    def _after_hide(self):
        self.setVisible(False)
        self.closed.emit()

    def _emit(self):
        if self.mode == "open":
            item = self.list.currentItem()
            if not item:
                return
            name = item.text().strip() + ".md"
        else:
            name = self.line.text().strip()
            if not name.endswith(".md"):
                name += ".md"
        if name:
            path = os.path.join(DATA_DIR, name)
            self.accepted.emit(path)
        self.hide_menu()

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() == QtCore.Qt.Key.Key_Escape:
                self.hide_menu()
                return True
            if obj in (self.ok_btn, self.cancel_btn) and event.key() in (
                QtCore.Qt.Key.Key_Return,
                QtCore.Qt.Key.Key_Enter,
            ):
                obj.click()
                return True
        return super().eventFilter(obj, event)

    def update_scale(self, font: QtGui.QFont, width: int):
        """Tilpas menuens font og bredde efter zoom."""
        self.setFont(font)
        for child in self.findChildren(QtWidgets.QWidget):
            child.setFont(font)
        if self.isVisible() and self.parent():
            w = int(width * 0.5)
            self.setFixedWidth(w)
            h = self.sizeHint().height()
            self.setFixedHeight(h)
            self.setGeometry((self.parent().width() - w) // 2, self.parent().height() - h, w, h)


class DeleteMenu(QtWidgets.QWidget):
    """Menu der kræver et haiku før en fil kan slettes."""

    confirmed = QtCore.pyqtSignal()
    closed = QtCore.pyqtSignal()

    haikus = [
        "Hvad vil du fortr\u00e6nge?\nHvad hvis det var begyndelse \u2013\nikke en fejlskrift?",
        "Du trykker for slet.\nMen hvem var du, da du skrev?\nEr han stadig her?",
        "Hver linje du skrev\nbar en dr\u00f8m i forkl\u00e6dning.\nEr du tr\u00e6t af den?",
        "Hvis du nu forlod\ndette fragment af din stemme \u2013\nhvem vil finde den?",
        "Glemsel er let nok,\nmen har du givet mening\ntil det, du vil fjerne?",
        "Skriv ikke forbi.\nSkriv en grav for ordene \u2013\nog g\u00e5 den i m\u00f8de.",
        "Den tavse cursor sp\u00f8r\u2019:\nSkal jeg forts\u00e6tte alene?\nEller med din h\u00e5nd?",
        "Et klik, og det g\u00e5r \u2013\nmen f\u00f8r du lader det ske,\nsig hvad det var v\u00e6rd.",
        "Afsked uden ord\ner bare fortr\u00e6ngningens dans.\nGiv det rytme f\u00f8rst.",
        "Du skrev det i hast \u2013\nvil du ogs\u00e5 slette det\ns\u00e5dan? Eller i haiku?",
        "M\u00e5ske var det grimt.\nMen var det ikke ogs\u00e5 dig?\n\u00c9n dag i dit liv.",
        "Dette var engang\net sted du t\u00e6nkte frit i.\nG\u00e5r du nu forbi?",
        "Du trykker p\u00e5 slet.\nMen vil du virkelig forlade\ndig selv i m\u00f8rket?",
        "Lad ikke din frygt\nblive sletterens skygge.\nSkriv med \u00e5bne \u00f8jne.",
        "Hvis du kan digte,\ns\u00e5 kan du ogs\u00e5 forlade \u2013\nmed hjertet \u00e5bent.",
        "Hvad flygter du fra?\nOrdene, du selv har valgt \u2013\neller det, de ser?",
        "Du skrev dette ned.\nVar det ikke sandt engang?\nHvor blev det af dig?",
        "Hvis du sletter nu,\nhvem er det s\u00e5, du fors\u00f8ger\nat tie ihjel?",
        "Der var en grund f\u00f8r \u2013\nen tanke, en f\u00f8lelse.\nHar den fortjent glemsel?",
        "Er du f\u00e6rdig nu?\nEller bare ut\u00e5lmodig\nefter at glemme?",
        "Du b\u00e6rer en stemme\nind i m\u00f8rket, uden spor.\nEr du sikker nu?",
        "Nogle ord skal v\u00e6k.\nMen f\u00f8rst m\u00e5 du fort\u00e6lle\nhvad de gjorde ved dig.",
        "Du har set forbi \u2013\nmen hvad var det, du s\u00e5 her?\nSkriv det i et vers.",
        "Slet kun det, du har\nmodet til at huske p\u00e5\nn\u00e5r tavsheden st\u00e5r.",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background:#121212;")
        self._index = 0
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(10, 10, 10, 10)

        self.intro = QtWidgets.QLabel(
            "Denne skrivemaskine er bygget til at skrive, ikke slette."
        )
        self.intro.setStyleSheet("color:#ccc;")
        self.intro.setWordWrap(True)
        self.intro.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.layout().addWidget(self.intro)

        self.haiku_label = QtWidgets.QLabel()
        self.haiku_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.haiku_label.setWordWrap(True)
        self.haiku_label.setStyleSheet("color:#ccc;")
        self.layout().addWidget(self.haiku_label)

        self.instruction = QtWidgets.QLabel(
            "Hvis du virkelig vil slette denne fil, skriv da et haiku om fortrydelse eller afslutning."
        )
        self.instruction.setStyleSheet("color:#ccc;")
        self.instruction.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.instruction.setWordWrap(True)
        self.instruction.hide()
        self.layout().addWidget(self.instruction)

        self.inputs = [QtWidgets.QLineEdit() for _ in range(3)]
        placeholders = [
            "5 stavelser",
            "7 stavelser",
            "5 stavelser",
        ]
        for inp in self.inputs:
            inp.hide()
            inp.setStyleSheet(
                "QLineEdit{border:1px solid #666;background:#121212;color:#ddd;}"
            )
            inp.textChanged.connect(self._validate)
            inp.installEventFilter(self)
            self.layout().addWidget(inp)
        for inp, ph in zip(self.inputs, placeholders):
            inp.setPlaceholderText(ph)
        self.inputs[-1].returnPressed.connect(self._confirm)

        btn_row = QtWidgets.QHBoxLayout()
        self.confirm_btn = QtWidgets.QPushButton("Slet")
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.clicked.connect(self._confirm)
        self.confirm_btn.setAutoDefault(True)
        self.confirm_btn.installEventFilter(self)
        self.confirm_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.next_btn = QtWidgets.QPushButton("Slet")
        self.next_btn.clicked.connect(self._start_inputs)
        self.next_btn.setAutoDefault(True)
        self.next_btn.installEventFilter(self)
        self.next_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.cancel_btn = QtWidgets.QPushButton("Annuller")
        self.cancel_btn.clicked.connect(self.hide_menu)
        self.cancel_btn.setAutoDefault(True)
        self.cancel_btn.installEventFilter(self)
        self.cancel_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        btn_row.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        btn_row.addWidget(self.confirm_btn)
        btn_row.addWidget(self.next_btn)
        btn_row.addWidget(self.cancel_btn)
        self.layout().addLayout(btn_row)
        self.confirm_btn.hide()

        self.hide()
        self.installEventFilter(self)

    def show_menu(self):
        if not self.parent():
            return
        parent = self.parent()
        width = int(parent.width() * 0.5)
        self.setFixedWidth(width)
        start = QtCore.QRect((parent.width() - width) // 2, parent.height(), width, parent.height())
        end = QtCore.QRect((parent.width() - width) // 2, 0, width, parent.height())
        self.setGeometry(start)
        self.setVisible(True)
        self.raise_()
        self._set_haiku()
        for inp in self.inputs:
            inp.hide()
        self.confirm_btn.hide()
        self.next_btn.show()
        self.cancel_btn.show()
        self.intro.show()
        self.haiku_label.show()
        self.instruction.hide()
        anim = QtCore.QPropertyAnimation(self, b"geometry")
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setDuration(200)
        anim.start()
        self._anim = anim
        self.next_btn.setFocus()

    def hide_menu(self):
        if not self.parent():
            self.hide()
            return
        parent = self.parent()
        end_rect = QtCore.QRect(self.x(), parent.height(), self.width(), parent.height())
        anim = QtCore.QPropertyAnimation(self, b"geometry")
        anim.setStartValue(self.geometry())
        anim.setEndValue(end_rect)
        anim.setDuration(200)
        anim.finished.connect(self._after_hide)
        anim.start()
        self._anim = anim

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() == QtCore.Qt.Key.Key_Escape:
                self.hide_menu()
                return True
            if obj in (self.confirm_btn, self.next_btn, self.cancel_btn) and event.key() in (
                QtCore.Qt.Key.Key_Return,
                QtCore.Qt.Key.Key_Enter,
            ):
                obj.click()
                return True
        return super().eventFilter(obj, event)

    def _after_hide(self):
        self.setVisible(False)
        self.closed.emit()

    def _set_haiku(self):
        text = self.haikus[self._index % len(self.haikus)]
        self._index += 1
        self.haiku_label.setText(text)

    def _start_inputs(self):
        for inp in self.inputs:
            inp.clear()
            inp.show()
        self.next_btn.hide()
        self.confirm_btn.show()
        self.intro.hide()
        self.haiku_label.hide()
        self.instruction.show()
        self._validate()
        self.inputs[0].setFocus()

    def _count_words(self, text: str) -> int:
        return len([w for w in text.strip().split() if w])

    def _validate(self):
        words = [self._count_words(inp.text()) for inp in self.inputs]
        ok = (
            3 <= words[0] <= 5
            and 4 <= words[1] <= 7
            and 3 <= words[2] <= 5
        )
        self.confirm_btn.setEnabled(ok)

    def _confirm(self):
        if self.confirm_btn.isEnabled():
            self.hide_menu()
            self.confirmed.emit()

    def update_scale(self, font: QtGui.QFont, width: int):
        """Opdater font og bredde efter zoom."""
        self.setFont(font)
        for child in self.findChildren(QtWidgets.QWidget):
            child.setFont(font)
        if self.isVisible() and self.parent():
            w = int(width * 0.5)
            self.setFixedWidth(w)
            self.setGeometry((self.parent().width() - w) // 2, 0, w, self.parent().height())


class PowerMenu(QtWidgets.QWidget):
    """Fuldskærmsmenu til strømstyring."""

    closed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(40, 40, 40, 40)
        self.layout().setSpacing(6)
        self.layout().setAlignment(
            QtCore.Qt.AlignmentFlag.AlignHCenter
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background:#121212;")

        actions = [
            ("Sluk maskinen", lambda: os.system("systemctl poweroff")),
            ("Genstart maskinen", lambda: os.system("systemctl reboot")),
            ("Luk X11", lambda: os.system("pkill X")),
            ("WiFi", self._toggle_wifi),
            ("\u00c5bn terminalvindue (LXTerminal)", lambda: os.system("lxterminal &")),
            ("\u00c5bn README", self._open_readme),
        ]
        self.wifi_enabled = self._wifi_status()
        self.buttons = []
        for text, func in actions:
            btn = QtWidgets.QPushButton(text)
            btn.clicked.connect(func)
            btn.setAutoDefault(True)
            btn.installEventFilter(self)
            self.layout().addWidget(btn)
            self.buttons.append(btn)
        # Gem reference til WiFi-knappen for senere opdatering
        self.wifi_btn = self.buttons[3]
        self._update_wifi_text()

        self.setVisible(False)
        self.setGeometry(0, 0, 0, 0)

    def _toggle_wifi(self):
        cmd = "nmcli radio wifi off" if self.wifi_enabled else "nmcli radio wifi on"
        os.system(cmd)
        self.wifi_enabled = not self.wifi_enabled
        self._update_wifi_text()

    def _wifi_status(self) -> bool:
        """Returner True hvis WiFi er tændt."""
        status = os.popen("nmcli radio wifi").read().strip().lower()
        return status == "enabled"

    def _update_wifi_text(self):
        state = "ON" if self.wifi_enabled else "OFF"
        if hasattr(self, "wifi_btn"):
            self.wifi_btn.setText(f"WiFi ({state})")
            self._update_button_width()

    def _update_button_width(self):
        margin = 20
        max_w = 0
        for btn in self.buttons:
            w = btn.fontMetrics().horizontalAdvance(btn.text())
            if w > max_w:
                max_w = w
        max_w += margin
        for btn in self.buttons:
            btn.setFixedWidth(max_w)

    def _open_readme(self):
        wnd = self.window()
        if hasattr(wnd, "open_readme"):
            wnd.open_readme()
        self.hide_menu()

    def show_menu(self):
        if not self.parent():
            return
        parent = self.parent()
        start_rect = QtCore.QRect(0, parent.height(), parent.width(), parent.height())
        end_rect = QtCore.QRect(0, 0, parent.width(), parent.height())
        self.setGeometry(start_rect)
        self.setVisible(True)
        self.raise_()
        wnd = self.window()
        if hasattr(wnd, "set_shortcuts_enabled"):
            wnd.set_shortcuts_enabled(False)
        anim = QtCore.QPropertyAnimation(self, b"geometry")
        anim.setStartValue(start_rect)
        anim.setEndValue(end_rect)
        anim.setDuration(200)
        if self.buttons:
            anim.finished.connect(self.buttons[0].setFocus)
        anim.start()
        self._anim = anim

    def hide_menu(self):
        if not self.parent():
            self.setVisible(False)
            return
        parent = self.parent()
        start_rect = self.geometry()
        end_rect = QtCore.QRect(0, parent.height(), parent.width(), parent.height())
        anim = QtCore.QPropertyAnimation(self, b"geometry")
        anim.setStartValue(start_rect)
        anim.setEndValue(end_rect)
        anim.setDuration(200)
        anim.finished.connect(self._after_hide)
        anim.start()
        self._anim = anim

    def _after_hide(self):
        self.setVisible(False)
        wnd = self.window()
        if hasattr(wnd, "set_shortcuts_enabled"):
            wnd.set_shortcuts_enabled(True)
        self.closed.emit()

    def update_scale(self, font: QtGui.QFont, width: int, height: int):
        """Opdater font og størrelse efter zoom."""
        self.setFont(font)
        for child in self.findChildren(QtWidgets.QWidget):
            child.setFont(font)
        if self.isVisible() and self.parent():
            self.setGeometry(0, 0, width, height)
            self.layout().activate()
        self._update_button_width()
        
    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() == QtCore.Qt.Key.Key_Escape:
                self.hide_menu()
                return True
            if obj in self.buttons:
                idx = self.buttons.index(obj)
                if event.key() in (
                    QtCore.Qt.Key.Key_Return,
                    QtCore.Qt.Key.Key_Enter,
                ):
                    obj.click()
                    return True
                if event.key() == QtCore.Qt.Key.Key_Down:
                    self.buttons[(idx + 1) % len(self.buttons)].setFocus()
                    return True
                if event.key() == QtCore.Qt.Key.Key_Up:
                    self.buttons[(idx - 1) % len(self.buttons)].setFocus()
                    return True
        return super().eventFilter(obj, event)


class MindMenu(QtWidgets.QWidget):
    """Menu med skrivepsykologiske funktioner."""

    toggledInvisible = QtCore.pyqtSignal(bool)
    toggledBlind = QtCore.pyqtSignal(bool)
    toggledHemi = QtCore.pyqtSignal(bool)
    startDestruct = QtCore.pyqtSignal(int)
    closed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background:#121212;color:#ddd;")
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(10, 10, 10, 10)

        self.invisible_cb = QtWidgets.QCheckBox("Usynlig blæk")
        self.layout().addWidget(self.invisible_cb)

        self.blind_cb = QtWidgets.QCheckBox("Skrive med øjnene lukkede")
        self.layout().addWidget(self.blind_cb)

        self.hemi_cb = QtWidgets.QCheckBox("Hemmingway mode")
        self.layout().addWidget(self.hemi_cb)

        self.blindstart_cb = QtWidgets.QCheckBox("Blindstart")
        self.layout().addWidget(self.blindstart_cb)

        sd_layout = QtWidgets.QHBoxLayout()
        sd_layout.addWidget(QtWidgets.QLabel("Selvdestruktion (min):"))
        self.sd_spin = QtWidgets.QSpinBox()
        self.sd_spin.setRange(5, 90)
        self.sd_spin.setValue(30)
        sd_layout.addWidget(self.sd_spin)
        self.sd_btn = QtWidgets.QPushButton("Start")
        sd_layout.addWidget(self.sd_btn)
        self.layout().addLayout(sd_layout)

        close_btn = QtWidgets.QPushButton("Luk")
        self.layout().addWidget(close_btn)

        self.invisible_cb.toggled.connect(self.toggledInvisible.emit)
        self.blind_cb.toggled.connect(self.toggledBlind.emit)
        self.hemi_cb.toggled.connect(self.toggledHemi.emit)
        self.sd_btn.clicked.connect(lambda: self.startDestruct.emit(self.sd_spin.value()))
        close_btn.clicked.connect(self.hide_menu)

        self.hide()

    def show_menu(self):
        if not self.parent():
            return
        parent = self.parent()
        width = int(parent.width() * 0.5)
        self.setFixedWidth(width)
        h = self.sizeHint().height()
        self.setFixedHeight(h)
        start = QtCore.QRect((parent.width() - width) // 2, parent.height(), width, h)
        end = QtCore.QRect((parent.width() - width) // 2, parent.height() - h, width, h)
        self.setGeometry(start)
        self.setVisible(True)
        self.raise_()
        anim = QtCore.QPropertyAnimation(self, b"geometry")
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setDuration(200)
        anim.start()
        self._anim = anim

    def hide_menu(self):
        if not self.parent():
            self.hide()
            return
        parent = self.parent()
        end_rect = QtCore.QRect(self.x(), parent.height(), self.width(), self.height())
        anim = QtCore.QPropertyAnimation(self, b"geometry")
        anim.setStartValue(self.geometry())
        anim.setEndValue(end_rect)
        anim.setDuration(200)
        anim.finished.connect(self._after_hide)
        anim.start()
        self._anim = anim

    def _after_hide(self):
        self.setVisible(False)
        self.closed.emit()

    def update_scale(self, font: QtGui.QFont, width: int):
        """Tilpas font og størrelse ved skalering."""
        self.setFont(font)
        for child in self.findChildren(QtWidgets.QWidget):
            child.setFont(font)
        if self.isVisible() and self.parent():
            parent = self.parent()
            w = int(width * 0.5)
            h = self.sizeHint().height()
            self.setFixedWidth(w)
            self.setFixedHeight(h)
            self.setGeometry((parent.width() - w) // 2, parent.height() - h, w, h)

class NotificationBar(QtWidgets.QStatusBar):
    """Statusbar der kan glide op og ned."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QStatusBar{background:#121212;color:#ddd;border-radius:6px;padding:4px;}"
        )
        shadow = QtWidgets.QGraphicsDropShadowEffect()
        shadow.setBlurRadius(8)
        shadow.setOffset(0, 0)
        self.setGraphicsEffect(shadow)
        self.setMaximumHeight(self.sizeHint().height())
        self._anim = None
        self.user_hidden = False

    def show_bar(self):
        end = self.sizeHint().height()
        anim = QtCore.QPropertyAnimation(self, b"maximumHeight")
        anim.setStartValue(0)
        anim.setEndValue(end)
        anim.setDuration(200)
        anim.start()
        self._anim = anim

    def hide_bar(self):
        end = self.maximumHeight()
        anim = QtCore.QPropertyAnimation(self, b"maximumHeight")
        anim.setStartValue(end)
        anim.setEndValue(0)
        anim.setDuration(200)
        anim.start()
        self._anim = anim

    def showMessage(self, message: str, timeout: int = 0) -> None:
        was_hidden = self.maximumHeight() == 0 and self.user_hidden
        if was_hidden:
            self.show_bar()
        super().showMessage(message, timeout)

    def clearMessage(self) -> None:
        super().clearMessage()
        self._maybe_hide()

    def _maybe_hide(self) -> None:
        if self.user_hidden:
            self.hide_bar()

# ----- Hovedvindue -----

class NotatorMainWindow(QtWidgets.QMainWindow):
    """Hovedklassen for programmet.

    Her samles alle widgets: timer, menu, faner og statuslinje. Layoutet
    er holdt enkelt for at kunne køre på svag hardware. Fonten sættes
    her globalt så alle under-widgets arver JetBrains Mono.
    """
    blind_typing: bool = False
    blind_visible: bool = False

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Notator")
        # Standardstørrelse inden fuldskærm
        self.resize(1280, 400)
        # Vis i frameless fullscreen
        self.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("background:#121212;")
        # Global font for hele applikationen. ``pick_mono_font`` sikrer
        # at der vælges en monospace-font som faktisk findes.
        self.font_family = pick_mono_font()
        base_font = QtGui.QFont(self.font_family, 10)
        self.setFont(base_font)

        # Fast zoom-niveau svarende til fem forstørrelses-trin
        self.scale_factor = 1.1 ** 5

        # Central widget indeholder timer og faner
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        radius = self._corner_radius()
        central.setStyleSheet(f"background:#121212;border-radius:{radius}px;")
        vlayout = QtWidgets.QVBoxLayout(central)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.setSpacing(0)

        # Topbaren indeholder kun timeren. Hemingway-knappen flyttes til
        # statuslinjen for at rydde op i layoutet.
        top_bar = QtWidgets.QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        vlayout.addLayout(top_bar)

        self.timer_widget = TimerWidget()
        self.timer_widget.timeout.connect(self.timer_finished)
        top_bar.addWidget(self.timer_widget)

        # Menuen til tidsvalg placeres lige under timeren og er skjult som standard
        self.timer_menu = TimerMenu()
        self.timer_menu.changed.connect(self._timer_selected)
        self.timer_menu.closed.connect(lambda: self.current_editor().setFocus())
        vlayout.addWidget(
            self.timer_menu, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter
        )

        # Fanelinje
        self.tabs = QtWidgets.QTabWidget()
        vlayout.addWidget(self.tabs)
        self._style_tabs()

        # Filmenu til åben/gem som overlay
        self.file_menu = FileMenu(central)
        self.file_menu.accepted.connect(self._file_action)
        self.file_menu.closed.connect(lambda: self.current_editor().setFocus())
        self.file_menu.hide()

        # Menu til sletning med haiku-beskyttelse
        self.delete_menu = DeleteMenu(central)
        self.delete_menu.confirmed.connect(self._delete_current_file)
        self.delete_menu.closed.connect(lambda: self.current_editor().setFocus())
        self.delete_menu.hide()

        # Menu til strømfunktioner
        self.power_menu = PowerMenu(central)
        self.power_menu.closed.connect(lambda: self.current_editor().setFocus())
        self.power_menu.hide()

        # Menu til skrivepsykologiske funktioner
        self.mind_menu = MindMenu(central)
        self.mind_menu.toggledInvisible.connect(self.set_invisible)
        self.mind_menu.toggledBlind.connect(self.set_blind_mode)
        self.mind_menu.toggledHemi.connect(self.set_hemingway)
        self.mind_menu.startDestruct.connect(self.start_self_destruct)
        self.mind_menu.closed.connect(lambda: self.current_editor().setFocus())
        self.mind_menu.hide()

        # Adskillelseslinje over statusbaren med blød skygge
        sep_layout = QtWidgets.QHBoxLayout()
        sep_layout.setContentsMargins(10, 0, 10, 0)
        line = QtWidgets.QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#333;")
        shadow = QtWidgets.QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setOffset(0, -2)
        line.setGraphicsEffect(shadow)
        sep_layout.addWidget(line)
        vlayout.addLayout(sep_layout)

        # Understregning som flyttes når aktiv fane skifter
        self.indicator = QtWidgets.QFrame(self.tabs.tabBar())
        # Mørk grågrøn farve i stedet for den tidligere klare grønne
        self.indicator.setStyleSheet("background:#334d33;")
        self.indicator.setFixedHeight(3)
        self.indicator.raise_()
        self.tabs.currentChanged.connect(self._move_indicator)
        self.tabs.tabBar().installEventFilter(self)

        # Notifikationsbar der glider op
        self.status = NotificationBar()
        self.setStatusBar(self.status)

        # Label der viser om Hemmingway-tilstand er aktiv
        self.hemi_label = QtWidgets.QLabel("Hemmingway aktiveret")
        self.hemi_label.setStyleSheet("color:#ddd;padding-right:6px;")
        self.hemi_label.hide()
        self.status.addPermanentWidget(self.hemi_label)

        self.invis_label = QtWidgets.QLabel("Usynlig blæk")
        self.invis_label.setStyleSheet("color:#ddd;padding-right:6px;")
        self.invis_label.hide()
        self.status.addPermanentWidget(self.invis_label)

        self.blind_label = QtWidgets.QLabel("Blindskrivning")
        self.blind_label.setStyleSheet("color:#ddd;padding-right:6px;")
        self.blind_label.hide()
        self.status.addPermanentWidget(self.blind_label)

        # Label til batteristatus
        self.battery_label = QtWidgets.QLabel()
        self.battery_label.setStyleSheet("color:#ddd;padding-left:6px;")
        self.status.addPermanentWidget(self.battery_label)

        # Opsæt overvågning af UPS HAT'en
        self.ups = UPSMonitor()
        self._battery_timer = QtCore.QTimer()
        self._battery_timer.timeout.connect(self.update_battery_status)
        self._battery_timer.start(30000)  # opdater hvert 30. sekund
        self.update_battery_status()

        # Interne tilstande
        self.hemingway = False
        self.last_timer_trigger = 0
        self.last_reset = 0
        self.current_duration = 0
        self.last_save_press = 0

        # Skrivepsykologiske tilstande
        self.invisible_enabled = False
        self.blind_typing = False
        self.blind_visible = False
        self.think_enabled = True

        self.invisible_delay = 5
        self.fade_speed = 1
        self._fading = False
        self._fade_word_start = 0
        self._fade_letter_index = None
        self._fade_alpha = 1.0
        self.invisible_idle = QtCore.QTimer()
        self.invisible_idle.setSingleShot(True)
        self.invisible_idle.timeout.connect(self._start_fade)
        self.fade_timer = QtCore.QTimer()
        self.fade_timer.timeout.connect(self._fade_word)

        self.think_delay = 300
        self.think_prompts = [
            "Hvad venter du på?",
            "Er du i gang med at redigere i dit hoved?",
            "Vil du hellere fortryde end skrive?",
            "Hvis du ikke skrev det her – hvem ville?",
        ]
        self.think_timer = QtCore.QTimer()
        self.think_timer.setSingleShot(True)
        self.think_timer.timeout.connect(self._think_prompt)
        self.set_think(True)

        self.self_destruct_timer = QtCore.QTimer()
        self.self_destruct_timer.timeout.connect(self._tick_self_destruct)
        self.self_destruct_seconds = 0

        # Load tidligere session eller start med en ny fane
        if not self.load_session():
            self.new_tab()
            self.apply_fixed_scale()

        # Gem sessionen løbende så åbne noter gendannes ved genstart
        self._session_timer = QtCore.QTimer()
        self._session_timer.timeout.connect(self.save_session)
        self._session_timer.start(10000)

        # Genveje
        self._setup_shortcuts()

        # Lyt globalt efter tabbar-resize og andre events
        QtWidgets.QApplication.instance().installEventFilter(self)

        # Efter vinduet er vist skal indikatorbjælken justeres
        QtCore.QTimer.singleShot(0, lambda: self._move_indicator(self.tabs.currentIndex()))
        # Sørg for fokus i skrivefeltet ved opstart
        QtCore.QTimer.singleShot(0, lambda: self.current_editor().setFocus())
        self._apply_corner_mask()

    # ----- Hjælpemetoder -----

    def _setup_shortcuts(self):
        """Opretter tastaturgenveje."""
        shortcuts = [
            ("Ctrl+N", self.new_tab),
            ("Ctrl+O", self.open_file),
            ("Ctrl+S", self.save_file),
            ("Ctrl+Shift+S", self.save_file_as),
            ("Ctrl+W", self.close_current_tab),
            ("Ctrl+Q", self.close),
            ("Ctrl+Shift+Tab", self.prev_tab),
            ("Ctrl+Tab", self.next_tab),
            # "Ctrl+Alt+Backspace" bruges traditionelt til at dr\u00e6be X11 og
            # kan derfor v\u00e6re deaktiveret p\u00e5 nogle systemer. Vi registrerer
            # derfor ogs\u00e5 en reserve-genvej.
            (["Ctrl+Alt+Backspace", "Ctrl+Alt+D"], self.request_delete),
            ("Ctrl+T", self.toggle_timer),
            ("Ctrl+R", self.reset_or_stop_timer),
            ("Ctrl+H", self.toggle_hemingway),
            ("Ctrl+Alt+.", self.toggle_tabbar),
            ("Ctrl+.", self.toggle_blind_visibility),
            ("Ctrl+M", self.toggle_mind_menu),
            ("F12", self.brightness_up),
            ("F11", self.brightness_down),
            ("Ctrl+Escape", self.power_menu.show_menu),
        ]
        self.shortcuts = []
        for seqs, slot in shortcuts:
            sequences = seqs if isinstance(seqs, (list, tuple)) else [seqs]
            for seq in sequences:
                sc = QtGui.QShortcut(QtGui.QKeySequence(seq), self)
                sc.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
                sc.setAutoRepeat(False)
                sc.activated.connect(slot)
                self.shortcuts.append(sc)

    def set_shortcuts_enabled(self, enabled: bool) -> None:
        """Aktiver eller deaktiver alle globale genveje."""
        for sc in getattr(self, "shortcuts", []):
            sc.setEnabled(enabled)

    def update_battery_status(self) -> None:
        """Hent data fra UPS HAT'en og opdater labelen."""
        pct, dis_mins, chg_mins, charging = self.ups.status()
        if pct is None:
            self.battery_label.setText("UPS ikke fundet")
            return
        if charging and chg_mins is not None:
            hours, minutes = divmod(chg_mins, 60)
            self.battery_label.setText(
                f"Batteri: {pct}% ({hours}t {minutes}m til fuld)"
            )
        elif dis_mins is not None:
            hours, minutes = divmod(dis_mins, 60)
            self.battery_label.setText(
                f"Batteri: {pct}% ({hours}t {minutes}m tilbage)"
            )
        else:
            self.battery_label.setText(f"Batteri: {pct}%")

    def eventFilter(self, obj, event):
        """Overvåg brugerinput og tabbar-resize for stabilt layout."""

        if event.type() in (
            QtCore.QEvent.Type.KeyPress,
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QEvent.Type.TouchBegin,
        ):
            self._user_typed()

        if obj is self.tabs.tabBar() and event.type() in (
            QtCore.QEvent.Type.Resize,
            QtCore.QEvent.Type.Show,
        ):
            QtCore.QTimer.singleShot(
                0, lambda idx=self.tabs.currentIndex(): self._move_indicator(idx)
            )
        return super().eventFilter(obj, event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_corner_mask()
        if self.timer_menu.isVisible() and self.timer_menu.parent():
            self.timer_menu.update_scale(self.font(), self.width())
        if self.file_menu.isVisible() and self.file_menu.parent():
            self.file_menu.update_scale(self.font(), self.width())
        if self.delete_menu.isVisible() and self.delete_menu.parent():
            self.delete_menu.update_scale(self.font(), self.width())
        if self.power_menu.isVisible() and self.power_menu.parent():
            self.power_menu.update_scale(self.font(), self.width(), self.height())

    def _corner_radius(self) -> int:
        dpi = self.logicalDpiX()
        return int(dpi * 0.5 / 2.54)

    def _apply_corner_mask(self) -> None:
        radius = self._corner_radius()
        path = QtGui.QPainterPath()
        rect = QtCore.QRectF(self.rect())
        path.addRoundedRect(rect, radius, radius)
        region = QtGui.QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)
        if self.centralWidget():
            self.centralWidget().setStyleSheet(
                f"background:#121212;border-radius:{radius}px;"
            )

    def _style_tabs(self, padding: int = 4):
        """Stil opsætningen af fanelinjen.

        ``padding`` justeres efter zoom-niveau for at holde
        proportionerne ens. Den grå linje over fanerne fjernes
        ved at fjerne alle kanter.
        """
        bar = self.tabs.tabBar()
        bar.setDrawBase(False)
        self.tabs.setDocumentMode(True)
        font_size = max(6, round(10 * self.scale_factor))
        self.tabs.setStyleSheet(
            "QTabBar {background:#121212;border:0;}"
            f"QTabBar::tab {{background:transparent;padding:{padding}px {padding*3}px;color:#aaa;border:none;font-size:{font_size}pt;}}"
            "QTabBar::tab:selected {color:#fff;}"
            "QTabWidget::pane {border:0;background:#121212;}"
        )
        if bar.isVisible():
            bar.setMaximumHeight(bar.sizeHint().height())

    def _move_indicator(self, index: int):
        """Flyt den grønne bjælke under den aktive fane med animation."""
        bar = self.tabs.tabBar()
        rect = bar.tabRect(index)
        end = QtCore.QRect(rect.left(), bar.height() - 3, rect.width(), 3)
        anim = QtCore.QPropertyAnimation(self.indicator, b"geometry")
        anim.setDuration(200)
        anim.setStartValue(self.indicator.geometry())
        anim.setEndValue(end)
        anim.start()
        self._indicator_anim = anim

    def _indicator_from_bottom(self):
        """Vis bjælken ved at glide op nedefra under den aktive fane."""
        bar = self.tabs.tabBar()
        rect = bar.tabRect(self.tabs.currentIndex())
        end_y = bar.sizeHint().height() - 3
        start_rect = QtCore.QRect(rect.left(), bar.sizeHint().height(), rect.width(), 3)
        self.indicator.setGeometry(start_rect)
        self.indicator.show()
        anim = QtCore.QPropertyAnimation(self.indicator, b"geometry")
        anim.setDuration(200)
        anim.setStartValue(start_rect)
        anim.setEndValue(QtCore.QRect(rect.left(), end_y, rect.width(), 3))
        anim.start()
        self._indicator_anim = anim

    def current_editor(self) -> NoteTab:
        """Returner det aktive NoteTab-objekt."""
        return self.tabs.currentWidget()

    # ----- Fanehåndtering -----

    def _generate_filename(self) -> str:
        """Lav et tidsstempel-navn i mappen til brugerdata."""
        os.makedirs(DATA_DIR, exist_ok=True)
        base = time.strftime("%H%M-%d%m%y")
        name = f"{base}.md"
        path = os.path.join(DATA_DIR, name)
        counter = 1
        while os.path.exists(path):
            name = f"{base}-{counter}.md"
            path = os.path.join(DATA_DIR, name)
            counter += 1
        return path

    def new_tab(self):
        """Opretter en ny tom fane med automatisk filnavn."""
        path = self._generate_filename()
        editor = NoteTab(path)
        editor.typed.connect(self._user_typed)
        index = self.tabs.addTab(editor, os.path.splitext(os.path.basename(path))[0])
        self.tabs.setCurrentIndex(index)
        # Flyt indikatorbjælken til den nye fane
        self._move_indicator(index)
        editor.auto_save()  # gem straks
        editor.setFont(QtGui.QFont(self.font_family, max(6, round(10 * self.scale_factor))))
        editor.set_scale(self.scale_factor)
        if self.blind_typing and not self.blind_visible:
            editor.set_blind(True)
        self.status.showMessage("Ny note oprettet", 2000)

    def open_file(self):
        """Vis eller skjul filmenuen for at åbne en fil."""
        if self.file_menu.isVisible() and self.file_menu.mode == "open":
            self.file_menu.hide_menu()
        else:
            self.file_menu.setup("open")
            self.file_menu.show_menu()

    def save_file(self):
        """Gem den aktuelle fane."""
        now = time.time()
        editor = self.current_editor()
        if now - self.last_save_press < 2:
            self.last_save_press = now
            self.save_file_as()
            return
        self.last_save_press = now

        path = getattr(editor, "file_path", None)
        # Hvis filen stadig har et autogenereret navn ønsker vi at
        # spørge brugeren om et bedre navn første gang der gemmes.
        if not path or getattr(editor, "auto_name", False):
            self.save_file_as()
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(editor.toPlainText())
        self.status.showMessage(f"Gemt {path}", 2000)

    def save_file_as(self):
        """Vis eller skjul menuen for at gemme under et nyt navn."""
        if self.file_menu.isVisible() and self.file_menu.mode == "save":
            self.file_menu.hide_menu()
        else:
            editor = self.current_editor()
            self.file_menu.setup(
                "save",
                os.path.splitext(os.path.basename(editor.file_path))[0] if editor.file_path else "note",
            )
            self.file_menu.show_menu()

    def _file_action(self, path: str):
        """Håndter resultatet fra filmenuen."""
        if self.file_menu.mode == "open":
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
                editor = NoteTab(path)
                editor.typed.connect(self._user_typed)
                editor.auto_name = False
                editor.setText(text)
                editor.setFont(QtGui.QFont(self.font_family, max(6, round(10 * self.scale_factor))))
                editor.set_scale(self.scale_factor)
                if getattr(self, "blind_typing", False) and not getattr(self, "blind_visible", False):
                    editor.set_blind(True)
                index = self.tabs.addTab(editor, os.path.splitext(os.path.basename(path))[0])
                self.tabs.setCurrentIndex(index)
                self._move_indicator(index)
                self.status.showMessage(f"Åbnede {path}", 2000)
            else:
                self.status.showMessage("Filen findes ikke", 2000)
        else:  # save
            editor = self.current_editor()
            with open(path, "w", encoding="utf-8") as f:
                f.write(editor.toPlainText())
            editor.file_path = path
            editor.auto_name = False
            name = os.path.splitext(os.path.basename(path))[0]
            self.tabs.setTabText(self.tabs.currentIndex(), name)
            self._move_indicator(self.tabs.currentIndex())
            self.status.showMessage(f"Gemt som {path}", 2000)

    def close_current_tab(self):
        """Lukker den aktuelle fane."""
        index = self.tabs.currentIndex()
        if index != -1:
            self.tabs.removeTab(index)
            if self.tabs.count() == 0:
                self.new_tab()
            self.status.showMessage("Fane lukket", 2000)
            self._move_indicator(self.tabs.currentIndex())

    def prev_tab(self):
        """Skift til forrige fane."""
        index = self.tabs.currentIndex()
        if index > 0:
            self.tabs.setCurrentIndex(index - 1)
            self._move_indicator(index - 1)

    def next_tab(self):
        """Skift til næste fane."""
        index = self.tabs.currentIndex()
        if index < self.tabs.count() - 1:
            self.tabs.setCurrentIndex(index + 1)
            self._move_indicator(index + 1)

    def toggle_tabbar(self):
        """Skjul eller vis fanelinjen med slide-animation."""
        bar = self.tabs.tabBar()
        end = bar.sizeHint().height()
        anim = QtCore.QPropertyAnimation(bar, b"maximumHeight")
        if bar.isVisible():
            anim.setStartValue(bar.height())
            anim.setEndValue(0)
            anim.finished.connect(lambda: bar.setVisible(False))
            self.indicator.hide()
            self.status.hide_bar()
            self.status.user_hidden = True
        else:
            bar.setVisible(True)
            anim.setStartValue(0)
            anim.setEndValue(end)
            QtCore.QTimer.singleShot(0, self._indicator_from_bottom)
            anim.finished.connect(lambda: self._move_indicator(self.tabs.currentIndex()))
            self.status.show_bar()
            self.status.user_hidden = False
        anim.setDuration(200)
        anim.start()
        self._tabbar_anim = anim

    # ----- Sletning af filer -----

    def request_delete(self):
        """Vis eller skjul menuen der kræver et haiku før sletning."""
        if self.delete_menu.isVisible():
            self.delete_menu.hide_menu()
        else:
            self.delete_menu.show_menu()

    def _delete_current_file(self):
        """Slet den aktuelle fil og lukk fanen."""
        editor = self.current_editor()
        path = getattr(editor, "file_path", "")
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                self.status.showMessage("Kunne ikke slette filen", 2000)
                return
        self.close_current_tab()
        self.status.showMessage("Ordene falder. Tomheden vinder.", 2000)

    def open_readme(self):
        """Vis README-filen i en skrivebeskyttet dialog."""
        path = os.path.join(ROOT_DIR, "README.md")
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            self.status.showMessage("Kunne ikke åbne README", 2000)
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("README")
        dlg.setLayout(QtWidgets.QVBoxLayout())
        view = QtWidgets.QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(text)
        view.setFont(QtGui.QFont(self.font_family, max(6, round(10 * self.scale_factor))))
        view.setStyleSheet("background:#121212;color:#e6e6e6;")
        dlg.layout().addWidget(view)
        dlg.resize(int(self.width() * 0.6), int(self.height() * 0.6))
        dlg.exec()

    # ----- Fast skalering -----

    def apply_fixed_scale(self):
        """Sæt fast fontstørrelse og layout ud fra ``scale_factor``."""
        font_size = max(6, round(10 * self.scale_factor))
        font = QtGui.QFont(self.font_family, font_size)
        self.setFont(font)
        self.tabs.tabBar().setFont(font)
        self.status.setFont(font)
        self.timer_menu.update_scale(font, self.width())
        self.file_menu.update_scale(font, self.width())
        self.delete_menu.update_scale(font, self.width())
        self.power_menu.update_scale(font, self.width(), self.height())
        if hasattr(self.mind_menu, "update_scale"):
            self.mind_menu.update_scale(font, self.width())
        self.timer_widget.update_font(int(16 * self.scale_factor))
        padding = int(4 * self.scale_factor)
        self._style_tabs(padding)
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            editor.setFont(font)
            editor.set_scale(self.scale_factor)
            editor.highlighter.rehighlight()
        QtCore.QTimer.singleShot(
            0, lambda idx=self.tabs.currentIndex(): self._move_indicator(idx)
        )

    # ----- Timerfunktioner -----

    def toggle_timer(self):
        """Vis eller skjul timer-menuen."""
        if self.timer_menu.isVisible():
            self.timer_menu.hide_menu()
        else:
            self.timer_menu.show_menu()

    def _timer_selected(self, seconds: int):
        """Start timeren med den valgte længde fra menuen."""
        if seconds:
            self.timer_widget.start(seconds)
            self.current_duration = seconds
            self.status.showMessage(
                f"Timer startet: {self.current_duration} sek", 2000
            )

    def reset_or_stop_timer(self):
        """Resetter timeren eller stopper den ved dobbelttryk."""
        now = time.time()
        if now - self.last_reset < 2:
            self.timer_widget.reset()
            self.status.showMessage("Timer stoppet", 2000)
            self.current_duration = 0
        else:
            if self.current_duration:
                self.timer_widget.start(self.current_duration)
                self.status.showMessage("Timer genstartet", 2000)
        self.last_reset = now

    def timer_finished(self):
        """Vis besked når tiden er gået."""
        self.status.showMessage("Tiden er gået", 5000)

    # ----- Lysstyrke -----

    def _brightness_path(self) -> str | None:
        paths = glob("/sys/class/backlight/*/brightness")
        return paths[0] if paths else None

    def _adjust_brightness(self, delta: int) -> None:
        path = self._brightness_path()
        if not path:
            self.status.showMessage("Ingen baggrundsbelysning fundet", 2000)
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                val = int(f.read().strip())
            val = max(0, min(255, val + delta))
            os.system(f"echo {val} | sudo tee {path} > /dev/null")
            self.status.showMessage(f"Lysstyrke {val}", 1000)
        except OSError:
            self.status.showMessage("Kan ikke justere lysstyrke", 2000)

    def brightness_up(self):
        self._adjust_brightness(10)

    def brightness_down(self):
        self._adjust_brightness(-10)

    # ----- Skrivepsykologi -----

    def set_invisible(self, state: bool) -> None:
        self.invisible_enabled = state
        self.invis_label.setVisible(state)
        self.mind_menu.invisible_cb.blockSignals(True)
        self.mind_menu.invisible_cb.setChecked(state)
        self.mind_menu.invisible_cb.blockSignals(False)
        if state:
            self.invisible_idle.start(self.invisible_delay * 1000)
        else:
            self.invisible_idle.stop()
            self.fade_timer.stop()
            self._fading = False

    def set_blind_mode(self, state: bool) -> None:
        self.blind_typing = state
        self.blind_visible = False
        self.blind_label.setVisible(state)
        self.mind_menu.blind_cb.blockSignals(True)
        self.mind_menu.blind_cb.setChecked(state)
        self.mind_menu.blind_cb.blockSignals(False)
        self._apply_blind()

    def toggle_blind_visibility(self):
        if not self.blind_typing:
            return
        self.blind_visible = not self.blind_visible
        self._apply_blind()

    def _apply_blind(self):
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            editor.set_blind(self.blind_typing and not self.blind_visible)

    def set_think(self, state: bool) -> None:
        self.think_enabled = state
        if state:
            self.think_timer.start(self.think_delay * 1000)
        else:
            self.think_timer.stop()

    def start_self_destruct(self, minutes: int) -> None:
        if minutes <= 0:
            return
        self.self_destruct_seconds = minutes * 60
        self.self_destruct_timer.start(1000)
        self.status.showMessage(f"Selvdestruktion om {minutes} min", 2000)

    def _tick_self_destruct(self) -> None:
        if self.self_destruct_seconds <= 0:
            return
        self.self_destruct_seconds -= 1
        if self.self_destruct_seconds == 60:
            self.status.showMessage("Selvdestruktion om 1 minut", 2000)
        if self.self_destruct_seconds <= 0:
            for i in range(self.tabs.count()):
                self.tabs.widget(i).clear()
            self.self_destruct_timer.stop()
            self.status.showMessage("Alt slettet", 5000)

    def _start_fade(self):
        if not self.invisible_enabled:
            return
        editor = self.current_editor()
        if not editor:
            return
        text = editor.toPlainText().rstrip()
        if not text:
            return
        last_space = text.rfind(" ")
        self._fade_word_start = last_space + 1 if last_space != -1 else 0
        self._fade_letter_index = len(text) - self._fade_word_start - 1
        self._fade_alpha = 1.0
        self._fading = True
        interval = max(10, int(1000 / (max(1, self.fade_speed) * 10)))
        self.fade_timer.start(interval)

    def _fade_word(self):
        editor = self.current_editor()
        if not editor or self._fade_letter_index is None:
            self.fade_timer.stop()
            self._fading = False
            return
        pos = self._fade_word_start + self._fade_letter_index
        cursor = editor.textCursor()
        cursor.setPosition(pos)
        cursor.movePosition(
            QtGui.QTextCursor.MoveOperation.NextCharacter,
            QtGui.QTextCursor.MoveMode.KeepAnchor,
        )
        color = QtGui.QColor("#e6e6e6")
        color.setAlphaF(self._fade_alpha)
        fmt = QtGui.QTextCharFormat()
        fmt.setForeground(color)
        cursor.mergeCharFormat(fmt)
        self._fade_alpha -= 0.1
        if self._fade_alpha <= 0:
            cursor.removeSelectedText()
            self._fade_alpha = 1.0
            self._fade_letter_index -= 1
            if self._fade_letter_index < 0:
                # fjern eventuel foranstående mellemrum
                if self._fade_word_start > 0:
                    cursor.setPosition(self._fade_word_start - 1)
                    cursor.movePosition(
                        QtGui.QTextCursor.MoveOperation.NextCharacter,
                        QtGui.QTextCursor.MoveMode.KeepAnchor,
                    )
                    if cursor.selectedText() == " ":
                        cursor.removeSelectedText()
                text = editor.toPlainText().rstrip()
                if not text:
                    self.fade_timer.stop()
                    self._fading = False
                    self._fade_letter_index = None
                else:
                    last_space = text.rfind(" ")
                    self._fade_word_start = last_space + 1 if last_space != -1 else 0
                    self._fade_letter_index = len(text) - self._fade_word_start - 1

    def _think_prompt(self):
        if not self.think_enabled:
            return
        import random

        self.status.showMessage(random.choice(self.think_prompts))

    def _user_typed(self):
        if self.invisible_enabled and not self._fading:
            self.invisible_idle.start(self.invisible_delay * 1000)
        if self._fading:
            self.fade_timer.stop()
            self._fading = False
        if self.think_enabled:
            self.status.clearMessage()
            self.think_timer.start(self.think_delay * 1000)

    def toggle_mind_menu(self):
        if self.mind_menu.isVisible():
            self.mind_menu.hide_menu()
        else:
            self.mind_menu.show_menu()

    # ----- Hemmingway-tilstand -----

    def set_hemingway(self, state: bool) -> None:
        self.hemingway = state
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            editor.hemingway = state
        self.hemi_label.setVisible(state)
        self.mind_menu.hemi_cb.blockSignals(True)
        self.mind_menu.hemi_cb.setChecked(state)
        self.mind_menu.hemi_cb.blockSignals(False)
        tilstand = "aktiveret" if state else "deaktiveret"
        self.status.showMessage(f"Hemmingway {tilstand}", 2000)

    def toggle_hemingway(self):
        """Aktiver eller deaktiver Hemingway Mode med genvej."""
        self.set_hemingway(not self.hemingway)

    # ----- Gem og genskab session -----

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.save_session()
        super().closeEvent(event)

    def save_session(self):
        """Gemmer information om den aktuelle session.

        Denne metode kaldes når vinduet lukkes og skriver en JSON-fil
        med stien til alle åbne filer samt vinduets placering. Ved næste
        opstart kan ``load_session`` bruge disse oplysninger til at
        genskabe arbejdsfladen.
        """
        os.makedirs(DATA_DIR, exist_ok=True)
        files: list[str] = []
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            path = getattr(w, "file_path", None)
            if path:
                files.append(path)
        data = {
            "files": files,
            "current": self.tabs.currentIndex(),
            "size": [self.width(), self.height()],
            "pos": [self.x(), self.y()],
        }
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def load_session(self) -> bool:
        """Forsøg at genskabe en tidligere session.

        Returnerer ``True`` hvis en session blev indlæst, ellers ``False``.
        Det betyder at programmet kan starte med tomme faner hvis der
        ikke eksisterer en ``session.json``. Metoden kigger på hver fil,
        åbner den hvis den findes, og genopretter også zoom-niveauet.
        """
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return False
        files = data.get("files", [])
        loaded = False
        for path in files:
            if path and os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
                editor = NoteTab(path)
                editor.typed.connect(self._user_typed)
                editor.auto_name = False
                editor.setText(text)
                if getattr(self, "blind_typing", False) and not getattr(self, "blind_visible", False):
                    editor.set_blind(True)
                self.tabs.addTab(editor, os.path.splitext(os.path.basename(path))[0])
                loaded = True
        if not loaded:
            return False
        self.tabs.setCurrentIndex(min(data.get("current", 0), self.tabs.count() - 1))
        size = data.get("size")
        if size:
            self.resize(*size)
        pos = data.get("pos")
        if pos:
            self.move(*pos)
        self.apply_fixed_scale()
        self._move_indicator(self.tabs.currentIndex())
        return True

# ----- Programstart -----

def main():
    app = QtWidgets.QApplication(sys.argv)
    dark = QtGui.QPalette()
    dark.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#121212"))
    dark.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor("#121212"))
    dark.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor("#e6e6e6"))
    app.setPalette(dark)
    # Ensartet udseende for knapper uafhængigt af window manager
    app.setStyleSheet(
        "QPushButton{background:#333;color:#ddd;border:none;border-radius:6px;padding:4px;}"
        "QPushButton:pressed{background:#555;}"
        "QPushButton:disabled{color:#555;background:#222;}"
    )
    window = NotatorMainWindow()
    window.showFullScreen()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
