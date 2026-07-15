import sys
import datetime
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QFileDialog, QTextEdit, QListWidget, QListWidgetItem, 
                             QAbstractItemView, QMessageBox, QHBoxLayout,QTabWidget)
from PyQt6.QtCore import QThread,QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt,QUrl
 
import mwclient
import keyring
from exif import Image as ExifImage
from exif_helper import ExifReader
import requests
import os
import shutil

from PyQt6.QtCore import QSettings

from description_worker import DescriptionGenerationThread

ORG_NAME = "trolleway"
APP_NAME = "turbo_wiki_uploader"

YELLOW4FORM = '#edf8b1'
BLACK4FORM = "#000000"
GRAY4FORM = "#8B8B8BFF"
USERAGENT = 'TurboWikiUploader/1.0  (trolleway@yandex.ru)'


class UploadThread(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)

    def __init__(self, username, password, file_path, file_name, short_description,long_description, depicts,locations):
        super().__init__()
        self.username = username
        self.password = password
        self.file_path = file_path
        self.file_name = file_name
        self.long_description = long_description 
        self.short_description = short_description 
        self.depicts = depicts
        self.locations = locations

    def run(self):
        try:
            self.log_signal.emit("Connecting to Wikimedia Commons...")
            site = mwclient.Site('commons.wikimedia.org', clients_useragent=USERAGENT)
            site.login(self.username, self.password)
            self.log_signal.emit("Login successful.")


            self.log_signal.emit(f"Uploading {self.file_name}...")
            

            with open(self.file_path, 'rb') as f:
                site.upload(f, self.file_name, self.long_description, ignore=False)
            
            self.log_signal.emit("Upload complete..")
            # 4. Execute the raw API Call (Updates descriptions and claims in one go)

            self.log_signal.emit("Writing Structured Data (Labels/Claims)...")
            
            payload = {}

            # Add English Description to SDC if text is provided
            if self.short_description.strip():
                payload['labels'] = {
                    'en': {
                        'language': 'en',
                        'value': self.short_description.strip()
                    }
                }
            payload['claims']={}
            if hasattr(self, 'locations') and self.locations:
                payload['claims']['P1071'] = []
                
                for qid in self.locations:
                    clean_qid = qid.strip()
                    if clean_qid.startswith('Q'):
                        payload['claims']['P1071'].append({
                            'mainsnak': {
                                'snaktype': 'value',
                                'property': 'P1071',
                                'datavalue': {
                                    'value': {
                                        'entity-type': 'item',
                                        'id': clean_qid
                                    },
                                    'type': 'wikibase-entityid'
                                }
                            },
                            'type': 'statement',
                            'rank': 'normal'
                        })    
                        
            if hasattr(self, 'depicts') and self.depicts:
                payload['claims']['P180'] = []
                
                for qid in self.depicts:
                    clean_qid = qid.strip()
                    if clean_qid.startswith('Q'):
                        payload['claims']['P180'].append({
                            'mainsnak': {
                                'snaktype': 'value',
                                'property': 'P180',
                                'datavalue': {
                                    'value': {
                                        'entity-type': 'item',
                                        'id': clean_qid
                                    },
                                    'type': 'wikibase-entityid'
                                }
                            },
                            'type': 'statement',
                            'rank': 'normal'
                        })    
                    
            token = site.get_token('csrf')
            entity_id = f"M{site.images[self.file_name].pageid}"
            # 4. Execute the raw API Call (Updates descriptions and claims in one go)
            if payload:
            
                self.log_signal.emit("Writing Structured Data (Labels/Claims)...")
                site.api('wbeditentity', 
                         id=entity_id, 
                         data=json.dumps(payload), 
                         token=token)
                self.log_signal.emit("Structured Data updated successfully!")
            else:
                self.log_signal.emit("No SDC data (text or GPS) to write.")

            self.log_signal.emit("Structured Data updated!")

            uploaded_folder_path = os.path.join(
                os.path.dirname(self.file_path), "commons_uploaded"
            )
            self.move_file_to_uploaded_dir(self.file_path, uploaded_folder_path)

            self.log_signal.emit("Done.")
            self.log_signal.emit("https://commons.wikimedia.org/wiki/File:"+self.file_name)
            self.finished_signal.emit(True)

        except Exception as e:
            # e.code holds 'fileexists-no-change'
            if e.code == 'fileexists-no-change':
                # Send a clean, readable message to your PyQt text box
                self.log_signal.emit(f"MediaWiki API Error ({e.code}): {e.info}")
                
                self.log_signal.emit("This file is an exact duplicate already on Commons. File will moved to /commons_duplicates folder")
           
            else:
                # Send other API errors (e.g., bad permissions, throttled)
                self.log_signal.emit(f"MediaWiki API Error ({e.code}): {e.info}")


        except Exception as e:
            self.log_signal.emit(f"Error: {str(e)}")
            self.finished_signal.emit(False)
            QMessageBox.critical(self, "Failed", "An error occurred. Check the log.")

    def move_file_to_uploaded_dir(self, filename, uploaded_folder_path):
        # move uploaded file to subfolder
        if not os.path.exists(uploaded_folder_path):
            os.makedirs(uploaded_folder_path)
        shutil.move(
            filename, os.path.join(uploaded_folder_path, os.path.basename(filename))
        )        
        






# Helper to format JSON for the API if mwclient doesn't auto-dump
import json
def import_json(d):
    return json.dumps(d)

class WikidataSearcher(QThread):
    """
    Background thread to search Wikidata without freezing the UI.
    """
    results_found = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.query_text = ""
        self.language = "en"

    def search(self, text):
        self.query_text = text
        self.start()

    def run(self):
        if not self.query_text:
            return

        try:
            # Wikidata API endpoint for entity search
            url = "https://www.wikidata.org/w/api.php"
            params = {
                "action": "wbsearchentities",
                "format": "json",
                "language": self.language,
                "search": self.query_text,
                "limit": 25,
                "type": "item"
            }
            headers = {'User-Agent': USERAGENT}
            
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            if 'search' in data:
                self.results_found.emit(data['search'])
            else:
                self.results_found.emit([])
                
        except Exception as e:

            self.error_occurred.emit(str(e))
            
class UploaderWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.selected_entities = [] # Stores dicts: {'id': 'Q..', 'label': '..'}
        self.selected_entities_location = [] # Stores dicts: {'id': 'Q..', 'label': '..'}
        
        self.initUI()
        
        # Search Logic Setup
        self.search_thread_location = WikidataSearcher()
        self.search_thread_location.results_found.connect(self.on_search_results_location)
        self.search_thread = WikidataSearcher()
        self.search_thread.results_found.connect(self.on_search_results)
        
        # Debounce Timer (prevents searching on every single keystroke)
        self.debounce_timer_location = QTimer()
        self.debounce_timer_location.setSingleShot(True)
        self.debounce_timer_location.setInterval(400) # Wait 400ms after user stops typing
        self.debounce_timer_location.timeout.connect(self.start_search_location)
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(400) # Wait 400ms after user stops typing
        self.debounce_timer.timeout.connect(self.start_search)
        self.file_path = None

    def initUI(self):
        self.setWindowTitle('Wikimedia Commons Uploader (PyQt6 + mwclient)')
        self.setGeometry(100, 100, 800, 600)
        
        main_layout = QHBoxLayout()
        left_layout = QVBoxLayout()
        
        # LEFT HALF

        self.user_input = QLineEdit(self)
        self.user_input.setPlaceholderText('Username')
        left_layout.addWidget(self.user_input)

        self.pass_input = QLineEdit(self)
        self.pass_input.setPlaceholderText('Password')
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        left_layout.addWidget(self.pass_input)

        self.file_btn = QPushButton('Select Photo', self)
        self.file_btn.clicked.connect(self.select_file)
        left_layout.addWidget(self.file_btn)

        
        self.image_label = QLabel('▭', self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Give the label a border to easily see the bounding area
        self.image_label.setStyleSheet("border: 1px dashed #aaa;") 
        left_layout.addWidget(self.image_label)
        
        self.labels_layout=QHBoxLayout()
        self.file_label = QLabel('No file selected', self)
        self.labels_layout.addWidget(self.file_label)
        
        
        # Hyperlink label (Simple text link)
        self.link_label = QLabel('', self)
        self.link_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Allows QLabel to automatically open local file URLs in the system viewer
        self.link_label.setOpenExternalLinks(True) 
        self.labels_layout.addWidget(self.link_label)

        left_layout.addLayout(self.labels_layout)

        
        left_layout.addWidget(QLabel("<b>Location or event (Wikidata Entity):</b>"))
        self.search_input_location = QLineEdit()
        self.search_input_location.setPlaceholderText("Type to search (e.g., 'Eiffel Tower', 'Abbey road')...")
        self.search_input_location.textChanged.connect(self.on_text_changed_location)
        left_layout.addWidget(self.search_input_location)

        # Suggestions List (Hidden by default)
        self.suggestions_list_location = QListWidget()
        self.suggestions_list_location.setVisible(False)
        self.suggestions_list_location.setMaximumHeight(150)
        self.suggestions_list_location.itemClicked.connect(self.add_entity_from_suggestion_location)
        left_layout.addWidget(self.suggestions_list_location)
 
        # Selected Entities List
        self.selected_list_location_widget = QListWidget()
        self.selected_list_location_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        # Apply some styling to make it look like a list of tags
        self.selected_list_location_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {YELLOW4FORM};
                border: 1px solid #ccc;
                border-radius: 4px;
            }}
            QListWidget::item {{
                border-bottom: 1px solid #e0e0e0;
                padding: 5px;
            }}

        """)
        left_layout.addWidget(QLabel("Selected Location:"))
        left_layout.addWidget(self.selected_list_location_widget)

 
        
        left_layout.addWidget(QLabel("<b>Depicts (Wikidata Entities):</b>"))

        #  Search Input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type to search (e.g., 'Cat')...")
        self.search_input.textChanged.connect(self.on_text_changed)
        left_layout.addWidget(self.search_input)

        # Suggestions List (Hidden by default)
        self.suggestions_list = QListWidget()
        self.suggestions_list.setVisible(False)
        self.suggestions_list.setMaximumHeight(150)
        self.suggestions_list.itemClicked.connect(self.add_entity_from_suggestion)
        left_layout.addWidget(self.suggestions_list)

        # 4. Selected Entities List
        self.selected_list_widget = QListWidget()
        self.selected_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        # Apply some styling to make it look like a list of tags
        self.selected_list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {YELLOW4FORM};
                border: 1px solid #ccc;
                border-radius: 4px;
            }}
            QListWidget::item {{
                border-bottom: 1px solid #e0e0e0;
                padding: 5px;
            }}

        """)
        #self.selected_list_widget.setStyleSheet("QListWidget { background-color: "+ YELLOW4FORM+"; color: white; }")
        #self.desc_input.setStyleSheet(f"background-color: {YELLOW4FORM}; color: {BLACK4FORM}; placeholder-text-color: {GRAY4FORM};")
        left_layout.addWidget(QLabel("Selected Entities:"))
        left_layout.addWidget(self.selected_list_widget)
        


        # RIGHT HALF
        right_layout = QVBoxLayout()
        
        # tab1
        tab_preset_01 = QWidget()
        layout_preset_01 = QVBoxLayout()
        self.gen_desc_btn_preset_01 = QPushButton('Generate Description: Place', self)
        self.gen_desc_btn_preset_01.clicked.connect(self.generate_description)
        layout_preset_01.addWidget(self.gen_desc_btn_preset_01)
        tab_preset_01.setLayout(layout_preset_01)

        # tab2
        tab_preset_02 = QWidget()
        layout_preset_02 = QVBoxLayout()
        self.gen_desc_btn_preset_02 = QPushButton('Generate Description: Thing in Place', self)
        self.gen_desc_btn_preset_02.clicked.connect(self.generate_description)
        layout_preset_02.addWidget(self.gen_desc_btn_preset_02)
        tab_preset_02.setLayout(layout_preset_02)

        # tab group
        self.label_preset_select = QLabel("Preset:")
        right_layout.addWidget(self.label_preset_select)
        self.tab_presets = QTabWidget()
        self.tab_presets.addTab(tab_preset_01, "Enter image coordinates")
        self.tab_presets.addTab(tab_preset_02, "Enter dest coordinates")
        self.tab_presets.setCurrentIndex(0)
        #self.tab_presets.currentChanged.connect(self.on_tab_change)
        self.tab_presets.setStyleSheet(
            """
            QTabWidget::pane { /* The tab widget frame */
                border: 2px solid black;
                position: absolute;
                top: -0.5em;
            }
            QTabBar::tab {
                background: lightgray;
                border: 1px solid black;
                padding: 5px;
            }
            QTabBar::tab:selected {
                background: white;
            }
        """
        )
        
        right_layout.addWidget(self.tab_presets)
        
        
        self.gen_desc_btn = QPushButton('Generate Description', self)
        self.gen_desc_btn.clicked.connect(self.generate_description)
        right_layout.addWidget(self.gen_desc_btn)

        right_layout.addWidget(QLabel("File name on Wikimedia Commons:"))
        self.filename_input = QLineEdit(self)
        self.filename_input.setPlaceholderText('Wikimedia Commons file name')
        self.filename_input.setStyleSheet(f"background-color: {YELLOW4FORM}; color: {BLACK4FORM}; placeholder-text-color: {GRAY4FORM};")
        right_layout.addWidget(self.filename_input)

        right_layout.addWidget(QLabel("English Description (going to SDC):"))
        self.desc_input = QTextEdit(self)
        self.desc_input.setPlaceholderText('Description for SDC')
        self.desc_input.setMaximumHeight(100)
        self.desc_input.setStyleSheet(f"background-color: {YELLOW4FORM}; color: {BLACK4FORM}; placeholder-text-color: {GRAY4FORM};")
        right_layout.addWidget(self.desc_input)

        right_layout.addWidget(QLabel("Wikitext for file"))
        self.large_desc_output = QTextEdit(self)
        self.large_desc_output.setStyleSheet(f"background-color: {YELLOW4FORM}; color: {BLACK4FORM}; placeholder-text-color: {GRAY4FORM};")
        self.large_desc_output.setPlaceholderText('Wikitext for file')
        # Size for 20 lines
        font_metrics = self.large_desc_output.fontMetrics()
        self.large_desc_output.setMinimumHeight(font_metrics.lineSpacing() * 30)
        right_layout.addWidget(self.large_desc_output)
        
        
        self.upload_btn = QPushButton('Upload', self)
        self.upload_btn.clicked.connect(self.start_upload)
        self.upload_btn.setEnabled(False)
        right_layout.addWidget(self.upload_btn)
        
        
        self.log_output = QTextEdit(self)
        self.log_output.setReadOnly(True)
        right_layout.addWidget(self.log_output)

        
        right_layout.addStretch()


        main_layout.addLayout(left_layout)
        main_layout.addLayout(right_layout)
        self.setLayout(main_layout)
        
        self.load_credentials()
        
    def select_file(self):
        settings = QSettings(ORG_NAME, APP_NAME)
        saved_file_dir = settings.value("file_dir", ".") # Default to dot   
        fname, _ = QFileDialog.getOpenFileName(self, 'Open file', saved_file_dir, "Image files (*.jpg *.jpeg *.png)")
        if fname:
            
            settings.setValue("file_dir",  os.path.dirname(fname))
        
            self.file_path = fname
            self.file_label.setText(fname.split('/')[-1])

            # Auto-suggest filename
            if not self.filename_input.text():
                self.filename_input.setText(fname.split('/')[-1])
            # If a file was selected, display it
        
            pixmap = QPixmap(self.file_path)    
            scaled_pixmap = pixmap.scaled(
                500, 
                500, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            
            self.image_label.setPixmap(scaled_pixmap)
            file_url = QUrl.fromLocalFile(self.file_path).toString()
            self.link_label.setText(f'<a href="{file_url}" style="color: #0066cc; text-decoration: underline;">Open original image in system viewer</a>')
            self.upload_btn.setEnabled(False)
            
    def generate_description(self):
        self.upload_btn.setEnabled(False)
        is_invalid_input = False
        if not self.file_path:
            QMessageBox.warning(self, "Error", "Please select a photo first.")
            is_invalid_input = True

        username = self.user_input.text()

        if self.user_input.text() == '':
            QMessageBox.warning(self, "Error", "Please enter a username first.")
            is_invalid_input = True
        
        if len(self.selected_wikidata_ids())<1:
            QMessageBox.warning(self, "Error", "Please select a wikidata objects first.")
            is_invalid_input = True
            
        if len(self.selected_wikidata_location_ids()) < 1 or len(self.selected_wikidata_location_ids()) > 1:
            QMessageBox.warning(self, "Error", "Please select a one location wikidata objects first.") 
            is_invalid_input = True
            
        if is_invalid_input:
            return
        # Disable the button to prevent multiple concurrent generations
        self.gen_desc_btn.setEnabled(False)
        self.log_output.append("Generating description...")

        # Initialize the background thread
        self.desc_thread = DescriptionGenerationThread(self.file_path, 
        username,self.selected_wikidata_ids(),
        self.selected_wikidata_location_ids(),
        USERAGENT)
        
        # Connect the worker signals to UI updater slots
        self.desc_thread.description_generated.connect(self.on_description_ready)
        self.desc_thread.log_signal.connect(self.log_output.append)
        
        # Re-enable the button when the thread finishes execution
        self.desc_thread.finished.connect(lambda: self.gen_desc_btn.setEnabled(True))
        
        # Launch the thread
        self.desc_thread.start()
        

    def on_description_ready(self, description_dict):
        """
        Receives the text from the background thread 
        and updates the text fields on the main thread safely.
        """
        self.filename_input.setText('name')
        self.desc_input.setText(description_dict['short_description'])
        self.filename_input.setText(description_dict['commons_filename'])
        
        # This writes the transferred text into your large QTextEdit
        self.large_desc_output.setText(description_dict['description'])
        self.log_output.append("Template generated successfully.")
        self.upload_btn.setEnabled(True)
        
        

    def save_credentials(self):
        """Saves credentials when the button is clicked."""
        # read to memory from fields
        username = self.user_input.text()
        password = self.pass_input.text()

        # 1. Save username to QSettings (Plain Text Config)
        from PyQt6.QtCore import QSettings
        settings = QSettings(ORG_NAME, APP_NAME)
        settings.setValue("username", username)

        # 2. Save password securely to System Keychain via keyring
        if username and password:
            keyring.set_password(APP_NAME, username, password)
            self.log_output.append("Credentials saved successfully.")
    
    def load_credentials(self):
        """Loads saved credentials into the input fields."""
        # 1. Load username from QSettings
        from PyQt6.QtCore import QSettings
        settings = QSettings(ORG_NAME, APP_NAME)
        saved_username = settings.value("username", "") # Default to empty string
        self.user_input.setText(saved_username)

        # 2. Load password from System Keychain
        if saved_username:
            saved_password = keyring.get_password(APP_NAME, saved_username)
            if saved_password:
                self.pass_input.setText(saved_password)            

    def start_upload(self):
        username = self.user_input.text()
        password = self.pass_input.text()
        target_name = self.filename_input.text()
        
        depicts = self.selected_wikidata_ids()
        depicts.append(self.selected_wikidata_location_ids()[0])
        
        self.save_credentials()

        if not (username and password and self.file_path and target_name):
            QMessageBox.warning(self, "Error", "Please fill in username, password, and generate description.")
            return
        if self.large_desc_output.toPlainText().strip()=='':
            QMessageBox.warning(self, "Error", "Please generate description frist")

        self.upload_btn.setEnabled(False)
        self.log_output.append("Starting process...")

        self.thread = UploadThread(username, password, self.file_path, target_name, self.desc_input.toPlainText(),self.large_desc_output.toPlainText(),depicts,self.selected_wikidata_location_ids())
        self.thread.log_signal.connect(self.log_output.append)
        self.thread.finished_signal.connect(self.on_finished)
        self.thread.start()

    def on_finished(self, success):
        self.upload_btn.setEnabled(False) #prevent from click upload second time
        if success:
            pass
        else:
            pass
            QMessageBox.critical(self, "Failed", "An error occurred. Check the log.")

    ##### Search wikidata entities
    
    def on_text_changed(self, text):

        if len(text.strip()) < 2:
            self.suggestions_list.hide()
            self.debounce_timer.stop()
            return
        
        # Reset timer on every keypress
        self.debounce_timer.start()
            
    def on_text_changed_location(self, text):

        if len(text.strip()) < 2:
            self.suggestions_list_location.hide()
            self.debounce_timer_location.stop()
            return
        
        # Reset timer on every keypress
        self.debounce_timer_location.start()
        

    def add_entity_from_suggestion(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        qid = data.get('id')

        # Prevent duplicates
        if any(e['id'] == qid for e in self.selected_entities):
            self.suggestions_list.hide()
            self.search_input.clear()
            return

        self.selected_entities.append(data)
        
        # Create a custom widget for the selected item (Label + Remove Button)
        self.add_selected_item_widget(data)
        
        # Reset Search
        self.search_input.clear()
        self.suggestions_list.hide()
        
    def add_entity_from_suggestion_location(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        qid = data.get('id')

        # Prevent duplicates
        if any(e['id'] == qid for e in self.selected_entities_location):
            self.suggestions_list_location.hide()
            self.search_input_location.clear()
            return

        self.selected_entities_location.append(data)
        
        # Create a custom widget for the selected item (Label + Remove Button)
        self.add_selected_item_widget_location(data)
        
        # Reset Search
        self.search_input.clear()
        self.suggestions_list.hide()
 
    def start_search(self):
        query = self.search_input.text().strip()
        if query:
            self.suggestions_list.clear()
            self.search_thread.search(query) 
    def start_search_location(self):
        query = self.search_input_location.text().strip()
        if query:
            self.suggestions_list.clear()
            self.search_thread_location.search(query)

    def on_search_results(self, results):
        self.suggestions_list.clear()
        
        if not results:
            self.suggestions_list.hide()
            return

        self.suggestions_list.setVisible(True)
        for item in results:
            # Format: Label (QID) - Description
            label = item.get('label', 'No Label')
            qid = item.get('id')
            desc = item.get('description', 'No description available')
            
            display_text = f"{label} ({qid})\t   ↳ {desc}"
            
            list_item = QListWidgetItem(display_text)
            # Store the actual data in the item for retrieval later
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.suggestions_list.addItem(list_item)

    def on_search_results_location(self, results):
        self.suggestions_list_location.clear()
        
        if not results:
            self.suggestions_list_location.hide()
            return

        self.suggestions_list_location.setVisible(True)
        for item in results:
            # Format: Label (QID) - Description
            label = item.get('label', 'No Label')
            qid = item.get('id')
            desc = item.get('description', 'No description available')
            
            display_text = f"{label} ({qid})\t   ↳ {desc}"
            
            list_item = QListWidgetItem(display_text)
            # Store the actual data in the item for retrieval later
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.suggestions_list_location.addItem(list_item)

    def add_entity_from_suggestion(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        qid = data.get('id')

        # Prevent duplicates
        if any(e['id'] == qid for e in self.selected_entities):
            self.suggestions_list.hide()
            self.search_input.clear()
            return

        self.selected_entities.append(data)
        
        # Create a custom widget for the selected item (Label + Remove Button)
        self.add_selected_item_widget(data)
        
        # Reset Search
        self.search_input.clear()
        self.suggestions_list.hide()

    def add_selected_item_widget(self, data):
        # Create a widget to hold the info and the delete button
        widget = QWidget()
        hbox = QHBoxLayout()
        hbox.setContentsMargins(5, 5, 5, 5)
        
        label_text = f"<b>{data.get('label', 'Unknown')}</b> ({data.get('id')})"
        desc_text = data.get('description', '')
        if desc_text:
            label_text += f"<br><small style='color:gray'>{desc_text}</small>"
            
        info_label = QLabel(label_text)
        info_label.setTextFormat(Qt.TextFormat.RichText)
        
        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(24, 24)
        remove_btn.setStyleSheet("color: red; font-weight: bold;")
        remove_btn.clicked.connect(lambda: self.remove_entity(data['id'], widget_item))

        hbox.addWidget(info_label)
        hbox.addStretch()
        hbox.addWidget(remove_btn)
        widget.setLayout(hbox)

        # Add to the list widget
        widget_item = QListWidgetItem(self.selected_list_widget)
        widget_item.setSizeHint(widget.sizeHint())
        self.selected_list_widget.setItemWidget(widget_item, widget)

    def add_selected_item_widget_location(self, data):
        # Create a widget to hold the info and the delete button
        widget = QWidget()
        hbox = QHBoxLayout()
        hbox.setContentsMargins(5, 5, 5, 5)
        
        label_text = f"<b>{data.get('label', 'Unknown')}</b> ({data.get('id')})"
        desc_text = data.get('description', '')
        if desc_text:
            label_text += f"<br><small style='color:gray'>{desc_text}</small>"
            
        info_label = QLabel(label_text)
        info_label.setTextFormat(Qt.TextFormat.RichText)
        
        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(24, 24)
        remove_btn.setStyleSheet("color: red; font-weight: bold;")
        remove_btn.clicked.connect(lambda: self.remove_entity_location(data['id'], widget_item))

        hbox.addWidget(info_label)
        hbox.addStretch()
        hbox.addWidget(remove_btn)
        widget.setLayout(hbox)

        # Add to the list widget
        widget_item = QListWidgetItem(self.selected_list_location_widget)
        widget_item.setSizeHint(widget.sizeHint())
        self.selected_list_location_widget.setItemWidget(widget_item, widget)

    def remove_entity(self, qid, widget_item):
        # Remove from data list
        self.selected_entities = [e for e in self.selected_entities if e['id'] != qid]
        
        # Remove from UI
        row = self.selected_list_widget.row(widget_item)
        self.selected_list_widget.takeItem(row)
    def remove_entity_location(self, qid, widget_item):
        # Remove from data list
        self.selected_entities_location = [e for e in self.selected_entities_location if e['id'] != qid]
        
        # Remove from UI
        row = self.selected_list_location_widget.row(widget_item)
        self.selected_list_location_widget.takeItem(row)
    
    def selected_wikidata_ids(self):
        """Returns list of QIDs for use in SDC upload"""
        return [e['id'] for e in self.selected_entities]
        
            
    def selected_wikidata_location_ids(self):
        """Returns list of QIDs for use in SDC upload"""
        return [e['id'] for e in self.selected_entities_location]


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = UploaderWindow()
    window.show()
    sys.exit(app.exec())
