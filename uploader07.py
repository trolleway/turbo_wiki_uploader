import sys
import datetime
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QFileDialog, QTextEdit, QListWidget, QListWidgetItem, 
                             QAbstractItemView, QMessageBox, QHBoxLayout)
from PyQt6.QtCore import QThread,QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt,QUrl
 
import mwclient
import keyring
from exif import Image as ExifImage
from exif_helper import ExifReader
import requests
import os

from PyQt6.QtCore import QSettings

from description_worker import DescriptionGenerationThread

ORG_NAME = "trolleway"
APP_NAME = "turbo_wiki_uploader"

YELLOW4FORM = '#edf8b1'
BLACK4FORM = "#000000"
GRAY4FORM = "#8B8B8BFF"



class UploadThread(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)

    def __init__(self, username, password, file_path, file_name, description):
        super().__init__()
        self.username = username
        self.password = password
        self.file_path = file_path
        self.file_name = file_name
        self.description = description # This text will be used for both wikitext and SDC


    def run(self):
        try:
            self.log_signal.emit("Connecting to Wikimedia Commons...")
            site = mwclient.Site('commons.wikimedia.org', clients_useragent='PyQt6Uploader/1.0')
            site.login(self.username, self.password)
            self.log_signal.emit("Login successful.")

            # 1. Upload the File (Wikitext layer)

            # 2. Extract EXIF Data
            exif_helper = ExifReader()
            exifdata = exif_helper.get_exif_data(self.file_path)
            


            # Add Claims (Coordinates + Heading) if coordinates exist
            if exifdata['lat'] and exifdata['lon']:
                self.log_signal.emit(f"Coords: {exifdata['lat']:.4f}, {exifdata['lon']:.4f}.")
            str_heading=''
            if exifdata['heading'] is not None:
                str_heading='|heading:'+str(exifdata['heading'])
                
            text = f"""=={{{{int:filedesc}}}}==
{{{{Information

|date={{{{Taken on|{exifdata['dt_iso']}|source=EXIF}}}}

|source={{{{Own work}}}}
|author=[[User:{self.username}|{self.username}]]
}}}}
{{{{Location dec|{exifdata['lat']}|{exifdata['lon']}{str_heading}}}}}

=={{{{int:license-header}}}}==
{{{{self|cc-by-sa-4.0}}}}
"""



            self.log_signal.emit(f"Uploading {self.file_name}...")
            

            self.log_signal.emit(str(text))
            #return
            with open(self.file_path, 'rb') as f:
                site.upload(f, self.file_name, text, ignore=True)
            
            self.log_signal.emit("Upload complete..")
            # 4. Execute the raw API Call (Updates descriptions and claims in one go)

            self.log_signal.emit("Writing Structured Data (Labels/Claims)...")
            
            payload = {}

            # Add English Description to SDC if text is provided
            if self.description.strip():
                payload['labels'] = {
                    'en': {
                        'language': 'en',
                        'value': self.description.strip()
                    }
                }
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


            self.log_signal.emit("Done.")
            self.finished_signal.emit(True)

        except APIError as e:
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
                "limit": 10,
                "type": "item"
            }
            headers = {'User-Agent': 'PyQt6Uploader/1.0'}
            
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            if 'search' in data:
                self.results_found.emit(data['search'])
            else:
                self.results_found.emit([])
                
        except Exception as e:
            self.log_signal.emit(f"Error: {str(e)}")
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

        self.file_label = QLabel('No file selected', self)
        left_layout.addWidget(self.file_label)
        
        self.image_label = QLabel('▭', self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Give the label a border to easily see the bounding area
        self.image_label.setStyleSheet("border: 1px dashed #aaa;") 
        left_layout.addWidget(self.image_label)
        
        # Hyperlink label (Simple text link)
        self.link_label = QLabel('', self)
        self.link_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Allows QLabel to automatically open local file URLs in the system viewer
        self.link_label.setOpenExternalLinks(True) 
        left_layout.addWidget(self.link_label)

        self.log_output = QTextEdit(self)
        self.log_output.setReadOnly(True)
        left_layout.addWidget(self.log_output)
        
        left_layout.addWidget(QLabel("<b>Location (Wikidata Entity):</b>"))
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
        self.gen_desc_btn = QPushButton('Generate Description', self)
        self.gen_desc_btn.clicked.connect(self.generate_description)
        right_layout.addWidget(self.gen_desc_btn)

        right_layout.addWidget(QLabel("Wikimedia Commons file name:"))
        self.filename_input = QLineEdit(self)
        self.filename_input.setPlaceholderText('Wikimedia Commons file name')
        self.filename_input.setStyleSheet(f"background-color: {YELLOW4FORM}; color: {BLACK4FORM}; placeholder-text-color: {GRAY4FORM};")
        right_layout.addWidget(self.filename_input)

        right_layout.addWidget(QLabel("File Description (going to SDC):"))
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
            self.upload_btn.setEnabled(True)
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
    
    def generate_description(self):
        if not self.file_path:
            QMessageBox.warning(self, "Error", "Please select a photo first.")
            return

        username = self.user_input.text()

        if self.user_input.text() == '':
            QMessageBox.warning(self, "Error", "Please enter a username first.")
            return
            
        # Disable the button to prevent multiple concurrent generations
        self.gen_desc_btn.setEnabled(False)
        self.log_output.append("Generating template in background thread...")

        # Initialize the background thread
        self.desc_thread = DescriptionGenerationThread(self.file_path, username)
        
        # Connect the worker signals to UI updater slots
        self.desc_thread.description_generated.connect(self.on_description_ready)
        self.desc_thread.log_signal.connect(self.log_output.append)
        
        # Re-enable the button when the thread finishes execution
        self.desc_thread.finished.connect(lambda: self.gen_desc_btn.setEnabled(True))
        
        # Launch the thread
        self.desc_thread.start()

    def on_description_ready(self, description_text):
        """
        Receives the text from the background thread 
        and updates the text fields on the main thread safely.
        """
        self.filename_input.setText('name')
        self.desc_input.setText('Description')
        
        # This writes the transferred text into your large QTextEdit
        self.large_desc_output.setText(description_text)
        self.log_output.append("Template generated successfully.")
        
        

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
        desc = self.desc_input.toPlainText()
        self.save_credentials()

        if not (username and password and self.file_path and target_name):
            QMessageBox.warning(self, "Error", "Please fill in all fields.")
            return

        self.upload_btn.setEnabled(False)
        self.log_output.append("Starting process...")

        self.thread = UploadThread(username, password, self.file_path, target_name, desc)
        self.thread.log_signal.connect(self.log_output.append)
        self.thread.finished_signal.connect(self.on_finished)
        self.thread.start()

    def on_finished(self, success):
        self.upload_btn.setEnabled(True)
        if success:
            QMessageBox.information(self, "Success", "Upload and data update complete!")
        else:
            pass
            #QMessageBox.critical(self, "Failed", "An error occurred. Check the log.")

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
            
            display_text = f"{label} ({qid})\n   ↳ {desc}"
            
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
            
            display_text = f"{label} ({qid})\n   ↳ {desc}"
            
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
    
    def get_selected_ids(self):
        """Returns list of QIDs for use in SDC upload"""
        return [e['id'] for e in self.selected_entities]
        
        
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = UploaderWindow()
    window.show()
    sys.exit(app.exec())
