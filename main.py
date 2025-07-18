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
from PyQt6 import QtWidgets, QtCore, QtGui
from smbus2 import SMBus

# Rodmappen til programmet bruges til at finde data-mappen
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

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
    kun de mest relevante: batteriprocent og den anslåede tid tilbage
    i minutter. Alle adresser er forudsat på I2C-adressen ``0x2d``.
    """

    ADDRESS = 0x2D
    REG_PERCENT_L = 0x24
    REG_PERCENT_H = 0x25
    REG_TIME_L = 0x28  # resterende afladningstid i minutter
    REG_TIME_H = 0x29

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

    def status(self) -> tuple[int | None, int | None]:
        """Returner (procent, minutter) eller (None, None) ved fejl."""
        try:
            pct = self._read_word(self.REG_PERCENT_L, self.REG_PERCENT_H)
            mins = self._read_word(self.REG_TIME_L, self.REG_TIME_H)
        except OSError:
            return None, None
        return pct, mins

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
        self.setStyleSheet(
            "background:#1a1a1a;color:#e6e6e6;"
            "QScrollBar{background:#1a1a1a;border:none;}"
            "QScrollBar::handle{background:#555;border-radius:4px;}"
            "QScrollBar::add-line,QScrollBar::sub-line{width:0;height:0;}"
            "QScrollBar::add-page,QScrollBar::sub-page{background:none;}"
        )
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
    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if self.hemingway:
            blocked = [QtCore.Qt.Key.Key_Backspace,
                       QtCore.Qt.Key.Key_Delete,
                       QtCore.Qt.Key.Key_Left,
                       QtCore.Qt.Key.Key_Up]
            if event.key() in blocked:
                # Bloker sletning og bevægelse bagud
                return
        super().keyPressEvent(event)

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
            bg = "#1a1a1a"
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
            "QLineEdit{border:1px solid #666;background:#1a1a1a;color:#ddd;}"
        )
        self.custom_input.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.custom_input.returnPressed.connect(self._custom)
        self.custom_input.installEventFilter(self)
        self.layout().addWidget(self.custom_input)

        # Starter skjult med højde 0; animationen ændrer "maximumHeight".
        self.setMaximumHeight(0)
        self.hide()

    def show_menu(self):
        """Vis menuen med en let slide-animation."""
        self.setVisible(True)
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

    @staticmethod
    def _fmt(seconds: int) -> str:
        return f"{seconds // 60 if seconds >= 60 else seconds} {'min' if seconds >= 60 else 'sek'}"


class FileMenu(QtWidgets.QWidget):
    """En simpel menu til filnavne der glider op fra bunden."""

    accepted = QtCore.pyqtSignal(str)
    closed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.list = QtWidgets.QListWidget()
        self.layout().addWidget(self.list)
        self.line = QtWidgets.QLineEdit()
        self.layout().addWidget(self.line)
        btns = QtWidgets.QHBoxLayout()
        self.ok_btn = QtWidgets.QPushButton()
        self.cancel_btn = QtWidgets.QPushButton("Annuller")
        btns.addWidget(self.ok_btn)
        btns.addWidget(self.cancel_btn)
        self.layout().addLayout(btns)

        self.ok_btn.clicked.connect(self._emit)
        self.cancel_btn.clicked.connect(self.hide_menu)
        self.line.installEventFilter(self)
        self.list.installEventFilter(self)
        self.line.returnPressed.connect(self._emit)
        self.list.itemActivated.connect(self._emit)
        self.setMaximumHeight(0)
        self.hide()

    def setup(self, mode: str, default: str = ""):
        """Konfigurer menuen til open eller save."""
        self.mode = mode
        self.ok_btn.setText("Åbn" if mode == "open" else "Gem")
        if mode == "open":
            self.line.hide()
            self.list.show()
            self.list.clear()
            data_dir = os.path.join(ROOT_DIR, "data")
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
        self.setVisible(True)
        end = self.sizeHint().height()
        anim = QtCore.QPropertyAnimation(self, b"maximumHeight")
        anim.setStartValue(0)
        anim.setEndValue(end)
        anim.setDuration(200)
        anim.start()
        self._anim = anim
        if self.mode == "open":
            self.list.setFocus()
        else:
            self.line.setFocus()

    def hide_menu(self):
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
            path = os.path.join(ROOT_DIR, "data", name)
            self.accepted.emit(path)
        self.hide_menu()

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.KeyPress and event.key() == QtCore.Qt.Key.Key_Escape:
            self.hide_menu()
            return True
        return super().eventFilter(obj, event)


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
            inp.textChanged.connect(self._validate)
            self.layout().addWidget(inp)
        for inp, ph in zip(self.inputs, placeholders):
            inp.setPlaceholderText(ph)
        self.inputs[-1].returnPressed.connect(self._confirm)

        btn_row = QtWidgets.QHBoxLayout()
        self.confirm_btn = QtWidgets.QPushButton("Slet")
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.clicked.connect(self._confirm)
        self.confirm_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.next_btn = QtWidgets.QPushButton("Slet")
        self.next_btn.clicked.connect(self._start_inputs)
        self.next_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.cancel_btn = QtWidgets.QPushButton("Annuller")
        self.cancel_btn.clicked.connect(self.hide_menu)
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

        self.setMaximumHeight(0)
        self.hide()

    def show_menu(self):
        self.setVisible(True)
        self._set_haiku()
        for inp in self.inputs:
            inp.hide()
        self.confirm_btn.hide()
        self.next_btn.show()
        self.cancel_btn.show()
        self.intro.show()
        self.haiku_label.show()
        self.instruction.hide()
        end = self.sizeHint().height()
        anim = QtCore.QPropertyAnimation(self, b"maximumHeight")
        anim.setStartValue(0)
        anim.setEndValue(end)
        anim.setDuration(200)
        anim.start()
        self._anim = anim
        self.next_btn.setFocus()

    def hide_menu(self):
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

# ----- Hovedvindue -----

class NotatorMainWindow(QtWidgets.QMainWindow):
    """Hovedklassen for programmet.

    Her samles alle widgets: timer, menu, faner og statuslinje. Layoutet
    er holdt enkelt for at kunne køre på svag hardware. Fonten sættes
    her globalt så alle under-widgets arver JetBrains Mono.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Notator")
        # Standardstørrelse inden fuldskærm
        self.resize(1280, 400)
        # Vis i frameless fullscreen
        self.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint)
        # Global font for hele applikationen. ``pick_mono_font`` sikrer
        # at der vælges en monospace-font som faktisk findes.
        self.font_family = pick_mono_font()
        base_font = QtGui.QFont(self.font_family, 10)
        self.setFont(base_font)

        # Standard zoom-niveau
        self.scale_factor = 1.0

        # Central widget indeholder timer og faner
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        vlayout = QtWidgets.QVBoxLayout(central)
        vlayout.setContentsMargins(0, 0, 0, 0)

        # Topbaren indeholder kun timeren. Hemingway-knappen flyttes til
        # statuslinjen for at rydde op i layoutet.
        top_bar = QtWidgets.QHBoxLayout()
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

        # Filmenu til åben/gem som glider op fra bunden
        self.file_menu = FileMenu()
        self.file_menu.accepted.connect(self._file_action)
        self.file_menu.closed.connect(lambda: self.current_editor().setFocus())
        vlayout.addWidget(self.file_menu)

        # Menu til sletning med haiku-beskyttelse
        self.delete_menu = DeleteMenu()
        self.delete_menu.confirmed.connect(self._delete_current_file)
        self.delete_menu.closed.connect(lambda: self.current_editor().setFocus())
        vlayout.addWidget(self.delete_menu)

        # Adskillelseslinje over statusbaren
        sep_layout = QtWidgets.QHBoxLayout()
        sep_layout.setContentsMargins(10, 0, 10, 0)
        line = QtWidgets.QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#444;")
        shadow = QtWidgets.QGraphicsDropShadowEffect()
        shadow.setBlurRadius(6)
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

        # Statuslinjen nederst viser midlertidige beskeder
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)
        # Gør statusbaren mere moderne og med samme farve som editoren
        self.status.setStyleSheet(
            "QStatusBar{background:#1a1a1a;color:#ddd;border-radius:6px;padding:4px;}"
        )
        shadow = QtWidgets.QGraphicsDropShadowEffect()
        shadow.setBlurRadius(8)
        shadow.setOffset(0, 0)
        self.status.setGraphicsEffect(shadow)

        # Hemingway-knappen lægges til højre i statuslinien
        self.hemi_button = QtWidgets.QToolButton()
        self.hemi_button.setCheckable(True)
        hemi_icon = QtGui.QIcon(os.path.join("icons", "feather.svg"))
        self.hemi_button.setIcon(hemi_icon)
        self.hemi_button.setIconSize(QtCore.QSize(24, 24))
        self.hemi_button.setStyleSheet(
            "QToolButton {background:#2c2c2c;border-radius:4px;}"
            "QToolButton:checked {background:#777;}"
        )
        self.hemi_button.setToolTip("Skift Hemingway Mode")
        self.hemi_button.clicked.connect(self.toggle_hemingway)
        self.status.addPermanentWidget(self.hemi_button)

        # Label til batteristatus lige efter Hemingway-knappen
        self.battery_label = QtWidgets.QLabel()
        self.battery_label.setStyleSheet("color:#ddd;padding-left:6px;")
        self.status.addPermanentWidget(self.battery_label)

        # Opsæt overvågning af UPS HAT'en
        self.ups = UPSMonitor()
        self._battery_timer = QtCore.QTimer()
        self._battery_timer.timeout.connect(self.update_battery_status)
        self._battery_timer.start(30000)  # opdater hvert 30. sekund
        self.update_battery_status()

        # Load tidligere session eller start med en ny fane
        if not self.load_session():
            self.new_tab()

        # Interne tilstande
        self.hemingway = False
        self.last_timer_trigger = 0
        self.last_reset = 0
        self.current_duration = 0
        self.last_save_press = 0

        # Genveje
        self._setup_shortcuts()

        # Efter vinduet er vist skal indikatorbjælken justeres
        QtCore.QTimer.singleShot(0, lambda: self._move_indicator(self.tabs.currentIndex()))
        # Sørg for fokus i skrivefeltet ved opstart
        QtCore.QTimer.singleShot(0, lambda: self.current_editor().setFocus())

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
            ("Ctrl+,", self.prev_tab),
            ("Ctrl+.", self.next_tab),
            ("Ctrl+Alt+Backspace", self.request_delete),
            ("Ctrl+T", self.toggle_timer),
            ("Ctrl+R", self.reset_or_stop_timer),
            ("Ctrl+H", self.toggle_hemingway),
            ("Ctrl+Alt+.", self.toggle_tabbar),
            ("Ctrl++", self.zoom_in),
            ("Ctrl+-", self.zoom_out),
        ]
        for seq, slot in shortcuts:
            sc = QtGui.QShortcut(QtGui.QKeySequence(seq), self)
            sc.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(slot)

    def update_battery_status(self) -> None:
        """Hent data fra UPS HAT'en og opdater labelen."""
        pct, mins = self.ups.status()
        if pct is None:
            self.battery_label.setText("UPS ikke fundet")
            return
        hours, minutes = divmod(mins, 60)
        self.battery_label.setText(
            f"Batteri: {pct}% ({hours}t {minutes}m tilbage)"
        )

    def eventFilter(self, obj, event):
        """Hold indikatorbjælken synkroniseret ved resize."""
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
        if self.timer_menu.isVisible() and self.timer_menu.parent():
            self.timer_menu.setFixedWidth(int(self.width() * 0.33))

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
            "QTabBar {background:#1a1a1a;}"
            f"QTabBar::tab {{background:transparent;padding:{padding}px {padding*3}px;color:#aaa;border:none;font-size:{font_size}pt;}}"
            "QTabBar::tab:selected {color:#fff;}"
            "QTabWidget::pane {border:none;background:#1a1a1a;}"
        )

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

    def current_editor(self) -> NoteTab:
        """Returner det aktive NoteTab-objekt."""
        return self.tabs.currentWidget()

    # ----- Fanehåndtering -----

    def _generate_filename(self) -> str:
        """Lav et tidsstempel-navn i mappen data."""
        data_dir = os.path.join(ROOT_DIR, "data")
        os.makedirs(data_dir, exist_ok=True)
        base = time.strftime("%H%M-%d%m%y")
        name = f"{base}.md"
        path = os.path.join(data_dir, name)
        counter = 1
        while os.path.exists(path):
            name = f"{base}-{counter}.md"
            path = os.path.join(data_dir, name)
            counter += 1
        return path

    def new_tab(self):
        """Opretter en ny tom fane med automatisk filnavn."""
        path = self._generate_filename()
        editor = NoteTab(path)
        index = self.tabs.addTab(editor, os.path.splitext(os.path.basename(path))[0])
        self.tabs.setCurrentIndex(index)
        # Flyt indikatorbjælken til den nye fane
        self._move_indicator(index)
        editor.auto_save()  # gem straks
        editor.setFont(QtGui.QFont(self.font_family, max(6, round(10 * self.scale_factor))))
        editor.set_scale(self.scale_factor)
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
                editor.auto_name = False
                editor.setText(text)
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
        else:
            bar.setVisible(True)
            anim.setStartValue(0)
            anim.setEndValue(end)
            # Placer bjælken under fanelinjen og lad den glide op
            rect = bar.tabRect(self.tabs.currentIndex())
            start_rect = QtCore.QRect(rect.left(), end, rect.width(), 3)
            self.indicator.setGeometry(start_rect)
            self.indicator.show()
            ind_anim = QtCore.QPropertyAnimation(self.indicator, b"geometry")
            ind_anim.setDuration(200)
            ind_anim.setStartValue(start_rect)
            ind_anim.setEndValue(QtCore.QRect(rect.left(), end - 3, rect.width(), 3))
            ind_anim.start()
            self._indicator_anim = ind_anim
            anim.finished.connect(lambda: self._move_indicator(self.tabs.currentIndex()))
        anim.setDuration(200)
        anim.start()
        self._tabbar_anim = anim

    # ----- Sletning af filer -----

    def request_delete(self):
        """Vis menuen der kræver et haiku før sletning."""
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

    # ----- Skalering -----

    def zoom_in(self):
        self._apply_scale(1.1)

    def zoom_out(self):
        self._apply_scale(0.9)

    def _apply_scale(self, factor: float):
        self.scale_factor *= factor
        font_size = max(6, round(10 * self.scale_factor))
        font = QtGui.QFont(self.font_family, font_size)
        self.setFont(font)
        self.tabs.tabBar().setFont(font)
        self.status.setFont(font)
        self.timer_menu.setFont(font)
        self.file_menu.setFont(font)
        self.delete_menu.setFont(font)
        self.timer_widget.update_font(int(16 * self.scale_factor))
        padding = int(4 * self.scale_factor)
        self._style_tabs(padding)
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            editor.setFont(font)
            editor.set_scale(self.scale_factor)
            editor.highlighter.rehighlight()
        if self.timer_menu.isVisible() and self.timer_menu.parent():
            self.timer_menu.setFixedWidth(int(self.width() * 0.33))
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

    # ----- Hemmingway-tilstand -----

    def toggle_hemingway(self):
        """Aktiver eller deaktiver Hemingway Mode.

        Hemmingway-tilstand forhindrer brugeren i at slette tekst eller
        bevæge markøren bagud. Funktionen kan slås til via genvejen
        ``Ctrl+H`` eller ved at klikke på pen-knappen i øverste højre hjørne.
        """
        self.hemingway = not self.hemingway
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            editor.hemingway = self.hemingway
        # Synkroniser knappen med den interne tilstand
        self.hemi_button.setChecked(self.hemingway)
        tilstand = "aktiveret" if self.hemingway else "deaktiveret"
        self.status.showMessage(f"Hemmingway {tilstand}", 2000)

    # ----- Gem og genskab session -----

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.save_session()
        super().closeEvent(event)

    def save_session(self):
        """Gemmer information om den aktuelle session.

        Denne metode kaldes når vinduet lukkes og skriver en JSON-fil
        med stien til alle åbne filer, hvilken fane der var aktiv samt
        det nuværende zoom-niveau. Ved næste opstart kan ``load_session``
        bruge disse oplysninger til at genskabe arbejdsfladen.
        """
        data = {
            "files": [self.tabs.widget(i).file_path for i in range(self.tabs.count())],
            "current": self.tabs.currentIndex(),
            "scale": self.scale_factor,
        }
        with open("session.json", "w", encoding="utf-8") as f:
            json.dump(data, f)

    def load_session(self) -> bool:
        """Forsøg at genskabe en tidligere session.

        Returnerer ``True`` hvis en session blev indlæst, ellers ``False``.
        Det betyder at programmet kan starte med tomme faner hvis der
        ikke eksisterer en ``session.json``. Metoden kigger på hver fil,
        åbner den hvis den findes, og genopretter også zoom-niveauet.
        """
        try:
            with open("session.json", "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return False
        files = data.get("files", [])
        if not files:
            return False
        for path in files:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
                editor = NoteTab(path)
                editor.auto_name = False
                editor.setText(text)
                self.tabs.addTab(editor, os.path.splitext(os.path.basename(path))[0])
        self.tabs.setCurrentIndex(min(data.get("current", 0), self.tabs.count()-1))
        self.scale_factor = data.get("scale", 1.0)
        self._apply_scale(1)  # anvend nuværende skala
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
