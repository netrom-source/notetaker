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

    def highlightBlock(self, text: str) -> None:
        # **fed**
        bold = QtCore.QRegularExpression(r"\*\*(.+?)\*\*")
        it = bold.globalMatch(text)
        while it.hasNext():
            match = it.next()
            self.setFormat(match.capturedStart(1), match.capturedLength(1), self.bold_format)

        # *kursiv*
        italic = QtCore.QRegularExpression(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)")
        it = italic.globalMatch(text)
        while it.hasNext():
            match = it.next()
            self.setFormat(match.capturedStart(1), match.capturedLength(1), self.italic_format)

        # overskrifter begynder med et eller flere #
        heading = QtCore.QRegularExpression(r"^(#{1,6})\s+(.*)")
        match = heading.match(text)
        if match.hasMatch():
            level = len(match.captured(1))
            fmt = QtGui.QTextCharFormat(self.heading_format)
            base = self.document().defaultFont().pointSizeF()
            # Jo færre #, jo større skrift
            scale = {1:2.0, 2:1.7, 3:1.5, 4:1.3, 5:1.2, 6:1.1}.get(level, 1)
            fmt.setFontPointSize(base * scale)
            self.setFormat(0, len(text), fmt)

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
        # Mørk baggrund og små marginer i siderne
        self.setStyleSheet("background:#1a1a1a;color:#e6e6e6")
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
            return
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
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
        self.hide()  # Timeren er skjult indtil den startes
        self._update_style()

    def start(self, seconds: int):
        """Start en nedtælling på det angivne antal sekunder."""
        self._duration = seconds
        self._remaining = seconds
        self._update_label()
        # Vis at timeren er aktiv med grøn baggrund
        self._running = True
        self._update_style()
        self.show()
        self._timer.start(1000)  # opdater hvert sekund

    def reset(self):
        """Stop og nulstil timeren."""
        self._timer.stop()
        self.hide()
        # Markér at timeren er stoppet
        self._running = False
        self._update_style()

    def _update_time(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self.timeout.emit()
            self.reset()
        else:
            self._update_label()

    def _update_label(self):
        mins, secs = divmod(self._remaining, 60)
        self.setText(f"{mins:02d}:{secs:02d}")

    def update_font(self, size: int):
        """Opdater fontstørrelsen og bevar farverne."""
        self._font_size = size
        self._update_style()

    def _update_style(self):
        """Anvend stylesheet afhængigt af om timeren kører."""
        bg = "#556b2f" if self._running else "#1a1a1a"
        self.setStyleSheet(
            f"background:{bg};color:#e6e6e6;font-size:{self._font_size}pt; padding:4px;"
        )

class TimerMenu(QtWidgets.QWidget):
    """En nedfældet menu hvor brugeren vælger timerens længde.

    Menuen erstatter den tidligere dialogboks og er nu integreret som en
    skjult widget under timer-displayet. ``changed``-signalet udsendes med
    det valgte antal sekunder, hvorefter menuen skjules igen.
    """

    changed = QtCore.pyqtSignal(int)
    presets = [30, 3 * 60, 7 * 60, 11 * 60]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.buttons = []
        for seconds in self.presets:
            btn = QtWidgets.QPushButton(self._fmt(seconds))
            btn.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
            btn.clicked.connect(lambda _, s=seconds: self._choose(s))
            btn.setAutoDefault(False)
            btn.installEventFilter(self)
            self.layout().addWidget(btn)
            self.buttons.append(btn)
        self.custom_input = QtWidgets.QLineEdit()
        self.custom_input.setPlaceholderText("min eller tal+s")
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
        anim.finished.connect(lambda: self.setVisible(False))
        anim.start()
        self._anim = anim

    def _choose(self, seconds: int):
        self.changed.emit(seconds)
        self.hide_menu()

    def _custom(self):
        text = self.custom_input.text().strip().lower()
        try:
            if text.endswith("s"):
                seconds = int(text[:-1])
            else:
                seconds = int(text) * 60
        except ValueError:
            QtWidgets.QMessageBox.warning(
                self, "Ugyldigt format",
                "Indtast et tal (minutter) eller med 's' for sekunder")
            return
        self.changed.emit(seconds)
        self.hide_menu()

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() == QtCore.Qt.Key.Key_Escape:
                self.hide_menu()
                return True
            # Navigér op/ned uden at forlade menuen
            if obj in self.buttons:
                idx = self.buttons.index(obj)
                if event.key() == QtCore.Qt.Key.Key_Down:
                    if idx == len(self.buttons) - 1:
                        self.custom_input.setFocus()
                    else:
                        self.buttons[idx + 1].setFocus()
                    return True
                if event.key() == QtCore.Qt.Key.Key_Up:
                    if idx == 0:
                        self.custom_input.setFocus()
                    else:
                        self.buttons[idx - 1].setFocus()
                    return True
            if obj is self.custom_input:
                if event.key() == QtCore.Qt.Key.Key_Up:
                    self.buttons[-1].setFocus()
                    return True
                if event.key() == QtCore.Qt.Key.Key_Down:
                    self.buttons[0].setFocus()
                    return True
        return super().eventFilter(obj, event)

    @staticmethod
    def _fmt(seconds: int) -> str:
        return f"{seconds // 60 if seconds >= 60 else seconds} {'min' if seconds >= 60 else 'sek'}"

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
        self.resize(800, 600)
        # Global font for hele applikationen. ``pick_mono_font`` sikrer
        # at der vælges en monospace-font som faktisk findes.
        self.font_family = pick_mono_font()
        base_font = QtGui.QFont(self.font_family, 10)
        self.setFont(base_font)

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
        vlayout.addWidget(self.timer_menu)

        # Fanelinje
        self.tabs = QtWidgets.QTabWidget()
        vlayout.addWidget(self.tabs)
        self._style_tabs()

        # Understregning som flyttes når aktiv fane skifter
        self.indicator = QtWidgets.QFrame(self.tabs.tabBar())
        self.indicator.setStyleSheet("background:#556b2f;")
        self.indicator.setFixedHeight(3)
        self.indicator.raise_()
        self.tabs.currentChanged.connect(self._move_indicator)

        # Statuslinjen nederst viser midlertidige beskeder
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)
        # Gør statusbaren mere moderne med afrundede hjørner og skygge
        self.status.setStyleSheet(
            "QStatusBar{background:rgba(0,0,0,150);color:#ddd;border-radius:6px;padding:4px;}"
        )
        shadow = QtWidgets.QGraphicsDropShadowEffect()
        shadow.setBlurRadius(8)
        shadow.setOffset(0, 0)
        self.status.setGraphicsEffect(shadow)

        # Hemingway-knappen lægges til højre i statuslinien
        self.hemi_button = QtWidgets.QToolButton()
        self.hemi_button.setCheckable(True)
        hemi_icon = QtGui.QIcon(os.path.join('icons', 'no-backspace.svg'))
        self.hemi_button.setIcon(hemi_icon)
        self.hemi_button.setIconSize(QtCore.QSize(16, 16))
        self.hemi_button.setStyleSheet(
            "QToolButton {background:transparent;}"
            "QToolButton:checked {background:#444;}"
        )
        self.hemi_button.setToolTip("Skift Hemingway Mode")
        self.hemi_button.clicked.connect(self.toggle_hemingway)
        self.status.addPermanentWidget(self.hemi_button)

        # Først angiv standard skalering
        self.scale_factor = 1.0

        # Load tidligere session eller start med en ny fane
        if not self.load_session():
            self.new_tab()

        # Interne tilstande
        self.hemingway = False
        self.last_timer_trigger = 0
        self.last_reset = 0
        self.current_duration = 0

        # Genveje
        self._setup_shortcuts()

    # ----- Hjælpemetoder -----

    def _setup_shortcuts(self):
        """Opretter tastaturgenveje."""
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+N"), self, self.new_tab)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+O"), self, self.open_file)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+S"), self, self.save_file)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+S"), self, self.save_file_as)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+W"), self, self.close_current_tab)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Q"), self, self.close)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+,"), self, self.prev_tab)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+."), self, self.next_tab)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+T"), self, self.toggle_timer)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+R"), self, self.reset_or_stop_timer)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+H"), self, self.toggle_hemingway)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Alt+."), self, self.toggle_tabbar)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl++"), self, self.zoom_in)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+-"), self, self.zoom_out)

    def _style_tabs(self, padding: int = 4):
        """Stil opsætningen af fanelinjen.

        ``padding`` justeres efter zoom-niveau for at holde
        proportionerne ens. Den grå linje over fanerne fjernes
        ved at fjerne alle kanter.
        """
        bar = self.tabs.tabBar()
        bar.setDrawBase(False)
        self.tabs.setDocumentMode(True)
        self.tabs.setStyleSheet(
            f"QTabBar::tab {{background:transparent;padding:{padding}px {padding*3}px;color:#aaa;border:none;}}"
            "QTabBar::tab:selected {color:#fff;}"
            "QTabWidget::pane {border:none;}"
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
        os.makedirs("data", exist_ok=True)
        base = time.strftime("%H%M-%d%m%y")
        name = f"{base}.md"
        path = os.path.join("data", name)
        counter = 1
        while os.path.exists(path):
            name = f"{base}-{counter}.md"
            path = os.path.join("data", name)
            counter += 1
        return path

    def new_tab(self):
        """Opretter en ny tom fane med automatisk filnavn."""
        path = self._generate_filename()
        editor = NoteTab(path)
        index = self.tabs.addTab(editor, os.path.basename(path))
        self.tabs.setCurrentIndex(index)
        # Flyt indikatorbjælken til den nye fane
        self._move_indicator(index)
        editor.auto_save()  # gem straks
        editor.setFont(QtGui.QFont(self.font_family, max(6, round(10 * self.scale_factor))))
        editor.set_scale(self.scale_factor)
        self.status.showMessage("Ny note oprettet", 2000)

    def open_file(self):
        """Åbn en eksisterende tekstfil i en ny fane."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Åbn fil", os.getcwd(), "Tekstfiler (*.md *.txt)")
        if path:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            editor = NoteTab(path)
            editor.auto_name = False
            editor.setText(text)
            index = self.tabs.addTab(editor, os.path.basename(path))
            self.tabs.setCurrentIndex(index)
            self._move_indicator(index)
            self.status.showMessage(f"Åbnede {path}", 2000)

    def save_file(self):
        """Gem den aktuelle fane."""
        editor = self.current_editor()
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
        """Gem den aktuelle fane som en ny fil."""
        editor = self.current_editor()
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Gem som", os.getcwd(), "Tekstfiler (*.md *.txt)")
        if path:
            if not path.endswith('.md'):
                path += '.md'
            with open(path, "w", encoding="utf-8") as f:
                f.write(editor.toPlainText())
            editor.file_path = path
            editor.auto_name = False
            self.tabs.setTabText(self.tabs.currentIndex(), os.path.basename(path))
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
            self.indicator.show()
            anim.finished.connect(lambda: self._move_indicator(self.tabs.currentIndex()))
        anim.setDuration(200)
        anim.start()
        self._tabbar_anim = anim

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
        self.timer_widget.update_font(int(16 * self.scale_factor))
        padding = int(4 * self.scale_factor)
        self._style_tabs(padding)
        self._move_indicator(self.tabs.currentIndex())
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            editor.setFont(font)
            editor.set_scale(self.scale_factor)

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
                self.tabs.addTab(editor, os.path.basename(path))
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
    window = NotatorMainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
