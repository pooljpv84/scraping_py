from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QLineEdit, QPushButton, QTextEdit
from .scraping import ScrapingService

#aaajjj
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Consulta de Información Educativa")
        self.setGeometry(100, 100, 600, 400)

        self.service = ScrapingService()  # Instanciar el servicio de scraping

        # Layout principal
        layout = QVBoxLayout()

        # Campo para ingresar la cédula
        self.cedula_label = QLabel("Ingrese la cédula:")
        self.cedula_input = QLineEdit()
        layout.addWidget(self.cedula_label)
        layout.addWidget(self.cedula_input)

        # Botón para consultar
        self.consultar_button = QPushButton("Consultar")
        self.consultar_button.clicked.connect(self.consultar_informacion)
        layout.addWidget(self.consultar_button)

        # Campo de texto para mostrar el resultado
        self.resultado_text = QTextEdit()
        self.resultado_text.setReadOnly(True)
        layout.addWidget(self.resultado_text)

        # Widget central
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def consultar_informacion(self):
        """Función que se ejecuta cuando se presiona el botón de consulta."""
        cedula = self.cedula_input.text()
        if cedula:
            resultado = self.service.obtener_informacion_educativa(cedula)
            self.resultado_text.setText(resultado)
        else:
            self.resultado_text.setText("Por favor, ingrese una cédula.")
