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
from PyQt6 import QtWidgets, QtCore, QtGui

# Fremhæv Markdown under skrivning
class MarkdownHighlighter(QtGui.QSyntaxHighlighter):
    """En simpel highlighter der viser Markdown-formatering direkte."""

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

        # overskrifter med #
        heading = QtCore.QRegularExpression(r"^(#+)\s+(.*)")
        match = heading.match(text)
        if match.hasMatch():
            self.setFormat(match.capturedStart(2), match.capturedLength(2), self.heading_format)

# ----- Hjælpeklasser -----

class NoteTab(QtWidgets.QTextEdit):
    """En teksteditor der kan blokere sletning i Hemmingway-tilstand."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hemingway = False  # Hvis sand, blokeres sletning og navigation bagud
        self.setFont(QtGui.QFont("JetBrains Mono", 10))
        self.setStyleSheet("background:#2b2b2b;color:#e6e6e6")
        self.highlighter = MarkdownHighlighter(self.document())
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
    """Et simpelt nedtællingsur øverst i vinduet."""
    timeout = QtCore.pyqtSignal()  # Signal der udsendes når tiden er gået

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("font-size: 16pt; padding: 4px;")
        self._duration = 0
        self._remaining = 0
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._update_time)
        self.hide()  # Timeren er skjult indtil den startes

    def start(self, seconds: int):
        """Start en nedtælling på det angivne antal sekunder."""
        self._duration = seconds
        self._remaining = seconds
        self._update_label()
        self.show()
        self._timer.start(1000)  # opdater hvert sekund

    def reset(self):
        """Stop og nulstil timeren."""
        self._timer.stop()
        self.hide()

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

class TimerDialog(QtWidgets.QDialog):
    """Dialog til valg af timerens længde."""

    # Prædefinerede tider i sekunder
    presets = [30, 3*60, 7*60, 11*60]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vælg tid")
        self.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
        self.setLayout(QtWidgets.QVBoxLayout())
        self.buttons = []
        for seconds in self.presets:
            btn = QtWidgets.QPushButton(self._fmt(seconds))
            self.layout().addWidget(btn)
            self.buttons.append(btn)
        self.custom_input = QtWidgets.QLineEdit()
        self.custom_input.setPlaceholderText("Skriv antal sekunder...")
        self.layout().addWidget(self.custom_input)
        self.selected_seconds = None

        # Tastaturnavigation mellem knapper med piletaster
        for btn in self.buttons:
            btn.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.custom_input.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

        # Knappernes handling
        for btn in self.buttons:
            btn.clicked.connect(self._preset_chosen)
        self.custom_input.returnPressed.connect(self._custom_chosen)
        self.custom_input.installEventFilter(self)

    def _preset_chosen(self):
        text = self.sender().text()
        value = int(text.split(' ')[0])
        if 'sek' in text:
            self.selected_seconds = value
        else:
            self.selected_seconds = value * 60
        self.accept()

    def _custom_chosen(self):
        try:
            self.selected_seconds = int(self.custom_input.text())
            self.accept()
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "Ugyldigt tal",
                                          "Indtast et heltal for minutter")

    def eventFilter(self, obj, event):
        """Sørger for at man kan gå tilbage til presets med pil op."""
        if obj is self.custom_input and event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() == QtCore.Qt.Key.Key_Up:
                self.buttons[-1].setFocus()
                return True
            if event.key() == QtCore.Qt.Key.Key_Down:
                return True  # lås fokus
        return super().eventFilter(obj, event)

    @staticmethod
    def _fmt(seconds: int) -> str:
        if seconds < 60:
            return f"{seconds} sek"
        else:
            return f"{seconds//60} min"

# ----- Hovedvindue -----

class NotatorMainWindow(QtWidgets.QMainWindow):
    """Hovedklassen for programmet."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Notator")
        self.resize(800, 600)

        # Central widget indeholder timer og faner
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        vlayout = QtWidgets.QVBoxLayout(central)
        vlayout.setContentsMargins(0, 0, 0, 0)

        # Timer øverst
        self.timer_widget = TimerWidget()
        self.timer_widget.timeout.connect(self.timer_finished)
        vlayout.addWidget(self.timer_widget)

        # Fanelinje
        self.tabs = QtWidgets.QTabWidget()
        vlayout.addWidget(self.tabs)

        # Statuslinje nederst
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)
        self.hemi_label = QtWidgets.QLabel("")
        self.status.addPermanentWidget(self.hemi_label)

        # Start med en enkelt tom fane
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

    def current_editor(self) -> NoteTab:
        """Returner det aktive NoteTab-objekt."""
        return self.tabs.currentWidget()

    # ----- Fanehåndtering -----

    def new_tab(self):
        """Opretter en ny tom fane."""
        editor = NoteTab()
        index = self.tabs.addTab(editor, "Untitled")
        self.tabs.setCurrentIndex(index)
        self.status.showMessage("Ny note oprettet", 2000)

    def open_file(self):
        """Åbn en eksisterende tekstfil i en ny fane."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Åbn fil",
                                                         os.getcwd(),
                                                         "Tekstfiler (*.txt);")
        if path:
            with open(path, 'r', encoding='utf-8') as f:
                text = f.read()
            editor = NoteTab()
            editor.setText(text)
            index = self.tabs.addTab(editor, os.path.basename(path))
            self.tabs.setCurrentIndex(index)
            editor.file_path = path
            self.status.showMessage(f"Åbnede {path}", 2000)

    def save_file(self):
        """Gem den aktuelle fane."""
        editor = self.current_editor()
        path = getattr(editor, 'file_path', None)
        if not path:
            self.save_file_as()
            return
        with open(path, 'w', encoding='utf-8') as f:
            f.write(editor.toPlainText())
        self.status.showMessage(f"Gemt {path}", 2000)

    def save_file_as(self):
        """Gem den aktuelle fane som en ny fil."""
        editor = self.current_editor()
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Gem som",
                                                         os.getcwd(),
                                                         "Tekstfiler (*.txt)")
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(editor.toPlainText())
            editor.file_path = path
            self.tabs.setTabText(self.tabs.currentIndex(),
                                 os.path.basename(path))
            self.status.showMessage(f"Gemt som {path}", 2000)

    def close_current_tab(self):
        """Lukker den aktuelle fane."""
        index = self.tabs.currentIndex()
        if index != -1:
            self.tabs.removeTab(index)
            if self.tabs.count() == 0:
                self.new_tab()
            self.status.showMessage("Fane lukket", 2000)

    def prev_tab(self):
        """Skift til forrige fane."""
        index = self.tabs.currentIndex()
        if index > 0:
            self.tabs.setCurrentIndex(index - 1)

    def next_tab(self):
        """Skift til næste fane."""
        index = self.tabs.currentIndex()
        if index < self.tabs.count() - 1:
            self.tabs.setCurrentIndex(index + 1)

    def toggle_tabbar(self):
        """Skjul eller vis fanelinjen."""
        bar = self.tabs.tabBar()
        bar.setVisible(not bar.isVisible())

    # ----- Timerfunktioner -----

    def toggle_timer(self):
        """Åbn dialogen til valg af tid."""
        self.show_timer_dialog()

    def show_timer_dialog(self):
        """Vis dialogen hvor brugeren vælger tiden."""
        dialog = TimerDialog(self)
        if dialog.exec():
            seconds = dialog.selected_seconds
            if seconds:
                self.timer_widget.start(seconds)
                self.current_duration = seconds
                self.status.showMessage(f"Timer startet: {self.current_duration} sek", 2000)

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
        """Slå Hemmingway-tilstand til eller fra."""
        self.hemingway = not self.hemingway
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            editor.hemingway = self.hemingway
        tilstand = "aktiveret" if self.hemingway else "deaktiveret"
        self.hemi_label.setText(f"Hemingway: {tilstand}")
        self.status.showMessage(f"Hemmingway {tilstand}", 2000)

# ----- Programstart -----

def main():
    app = QtWidgets.QApplication(sys.argv)
    window = NotatorMainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
