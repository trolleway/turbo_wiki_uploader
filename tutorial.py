# Файл: wizard.py
from PyQt6.QtWidgets import QWizard, QWizardPage, QVBoxLayout, QLabel
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

class WelcomePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Добро пожаловать!")
        layout = QVBoxLayout()
        label = QLabel("Этот мастер поможет вам разобраться с функциями программы.")
        label.setWordWrap(True)
        layout.addWidget(label)
        self.setLayout(layout)

class StepOnePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Шаг 1: Создание проекта")
        layout = QVBoxLayout()
        text_label = QLabel("Нажмите на кнопку 'Новый проект' на панели инструментов.")
        text_label.setWordWrap(True)
        layout.addWidget(text_label)
        
        img_label = QLabel()
        pixmap = QPixmap("step1.png")
        if not pixmap.isNull():
            img_label.setPixmap(pixmap.scaled(400, 300, Qt.AspectRatioMode.KeepAspectRatio))
        else:
            img_label.setText("[Скриншот step1.png]")
        layout.addWidget(img_label)
        self.setLayout(layout)

class TutorialWizard(QWizard):
    """Главный класс туториала, который мы будем импортировать"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Руководство пользователя")
        self.addPage(WelcomePage())
        self.addPage(StepOnePage())
        self.resize(500, 450)