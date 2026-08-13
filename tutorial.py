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

class PageLogin(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Log In")
        layout = QVBoxLayout()
        text_label = QLabel("Enter your Wikimedia Commons credentials in the Username and Password fields located at the top-left corner of the window.")
        text_label.setWordWrap(True)
        layout.addWidget(text_label)
        '''
        img_label = QLabel()
        pixmap = QPixmap("step1.png")
        if not pixmap.isNull():
            img_label.setPixmap(pixmap.scaled(400, 300, Qt.AspectRatioMode.KeepAspectRatio))
        else:
            img_label.setText("[Скриншот step1.png]")
        layout.addWidget(img_label)
        '''
        self.setLayout(layout)

class PageSelectFile(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Select Your Photo")
        layout = QVBoxLayout()
        txt='''Click Select Photo and choose a JPEG file.
<p>Requirements: The photo must contain EXIF geolocation data (coordinates) to ensure it appears correctly on maps. It also requires an original capture date.</p>
<p>Tip: If your photo lacks coordinates, you can add them using tools like GeoSetter or Rasklad Geotag.</p>
<p>Quality: Always upload original, full-resolution files. Do not resize them.</p>
<br>
<p>
Once selected, the camera location will appear on the map. You can drag the marker to adjust the position if needed.</p>'''
        text_label = QLabel()
        text_label.setTextFormat(Qt.TextFormat.RichText)
        text_label.setText(txt)
        text_label.setWordWrap(True)
        layout.addWidget(text_label)

        self.setLayout(layout)

class PagePresets(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Choose a Description Preset")
        layout = QVBoxLayout()
        txt='''
This uploader simplifies the process by generating descriptions based on Wikidata items.
<p>Choose the preset that best fits your image:
<ul>
<li>Geographic Object: Use this for specific entities that already have their own Wikidata entry (e.g., a specific building, street, village, or train station).
<li>Object in Place: Best for generic items located in a specific area. You select the object type and the location separately. The uploader will find intersecting categories, such as "Lampposts in Warsaw."
<li>Address on Street: Use this for buildings that don't have their own Wikidata entry but are located on a street that does.
<li>Automobile: A specialized preset for uploading photos of cars.
</ul>
'''
        text_label = QLabel()
        text_label.setTextFormat(Qt.TextFormat.RichText)
        text_label.setText(txt)
        text_label.setWordWrap(True)
        layout.addWidget(text_label)

        self.setLayout(layout)

class PageWikidata(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Link to Wikidata")
        layout = QVBoxLayout()
        txt='''After selecting your image and preset (e.g., Geographic Object or Object in Place), enter the object type and location name in the respective fields.
A list of matching Wikidata items will appear.Click on the correct item to link it to your upload.
'''
        text_label = QLabel()
        text_label.setTextFormat(Qt.TextFormat.RichText)
        text_label.setText(txt)
        text_label.setWordWrap(True)
        layout.addWidget(text_label)

        self.setLayout(layout)

class PageUpload(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Generate description and upload file")
        layout = QVBoxLayout()
        txt='''Click the Generate Description button.
The tool will automatically search for existing Wikimedia Commons categories and generate a file name and description text.
Review the generated text and categories; you can manually edit them if necessary.
<p>
Click Upload to finish.
Once the upload is successful, the local file will be moved to a commons_uploaded subfolder on your disk to help you keep track of processed files.
'''
        text_label = QLabel()
        text_label.setTextFormat(Qt.TextFormat.RichText)
        text_label.setText(txt)
        text_label.setWordWrap(True)
        layout.addWidget(text_label)

        self.setLayout(layout)
                        
class TutorialWizard(QWizard):
    """Главный класс туториала, который мы будем импортировать"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Руководство пользователя")
        self.addPage(WelcomePage())
        self.addPage(PageLogin())
        self.addPage(PageSelectFile())
        self.addPage(PagePresets())
        self.addPage(PageWikidata())
        self.addPage(PageUpload())
        self.resize(500, 450)
        
        '''
        Введите логин и пароль от своего аккаунта на wikimedia commons in 'username' and 'password' line edits at top left of window.
2. Нажмите Select Photo, и выберите фотографию в формате JPEG. Для загрузки обязательно чтобы в фотографии были записаны географические координаты в EXIF, чтобы их было видно на картах. Для записи координат вы можете использовать приложения GeoSetter, Rasklad Geotag. Так же необходима дата съёмки. Загружайте исходные файлы, без уменьшения размера. После выбора фотографии на карте отобразится местонааождение камеры, его можно пододвинуть.
3. Этот загрузчик отличается от других тем, что в нём есть несколько пресетов описаний, и сами описания генерируются исходя из выбранных записей wikidata. Geographic Object для фото какого-либо географического объекта, у которого есть своя запись в wikidata: здание, улица, посёлок, станция. Object in place - некоторая вещь в городе, в этом пресете выбирается wikidata объект для вещи и для местности, и загрузчик находит подходящие категории типа "фонарные столбы в Варшаве". Address on street - для фотографий зданий с известным адресом, у которых нет своего объекта Wikidata, но есть объект Wikidata для улицы. Automobile - пресет для загрузки фото автомобилей
4. Теперь выберите изображение, выберите пресет Geographic Object либо Object in Place. Введите в поля тип объекта и населёный пункт, вам будет предложен список найденых объектов Wikidata, кликните на один, чтобы он стал использоваться.
5. Нажмите кнопку "Generate Description". Загрузчик начнёт искать необходимые категории, существующие в Wikimedia Commons, и сгенерирует название и текст описания файла. При желании вы можете их исправить.
6. Можно нажимать кнопку Upload. Файл загрузится. На диске будет создана подкаталог commons_uploaded, и файл будет перемещён в неё, чтобы не было путаницы. 
        
        '''
        '''
How to Use the WikiCommons PyQt Uploader
Log In
Enter your Wikimedia Commons credentials in the Username and Password fields located at the top-left corner of the window.
Select Your Photo
Click Select Photo and choose a JPEG file.
Requirements: The photo must contain EXIF geolocation data (coordinates) to ensure it appears correctly on maps. It also requires an original capture date.
Tip: If your photo lacks coordinates, you can add them using tools like GeoSetter or Rasklad Geotag.
Quality: Always upload original, full-resolution files. Do not resize them.
Once selected, the camera location will appear on the map. You can drag the marker to adjust the position if needed.

Choose a Description Preset
This uploader simplifies the process by generating descriptions based on Wikidata items.
Choose the preset that best fits your image:
Geographic Object: Use this for specific entities that already have their own Wikidata entry (e.g., a specific building, street, village, or train station).
Object in Place: Best for generic items located in a specific area. You select the object type and the location separately. The uploader will find intersecting categories, such as "Lampposts in Warsaw."
Address on Street: Use this for buildings that don't have their own Wikidata entry but are located on a street that does.
Automobile: A specialized preset for uploading photos of cars.
Link to Wikidata
After selecting your image and preset (e.g., Geographic Object or Object in Place), enter the object type and location name in the respective fields.
A list of matching Wikidata items will appear.Click on the correct item to link it to your upload.
Generate Metadata
Click the Generate Description button.
The tool will automatically search for existing Wikimedia Commons categories and generate a file name and description text.
Review the generated text and categories; you can manually edit them if necessary.UploadClick Upload to finish.
Once the upload is successful, the local file will be moved to a commons_uploaded subfolder on your disk to help you keep track of processed files.

        '''
        