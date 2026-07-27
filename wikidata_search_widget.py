# wikidata_search_widget.py
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLineEdit, QListWidget, 
                             QListWidgetItem, QLabel, QPushButton, QHBoxLayout,
                             QAbstractItemView)
from PyQt6.QtCore import QThread, pyqtSignal, QTimer, Qt
import requests

USERAGENT = 'TurboWikiUploader/1.0  (trolleway@yandex.ru)'

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

class WikidataSearchWidget(QWidget):
    """
    A reusable widget for searching and selecting Wikidata entities.
    Emits a signal when entities are selected/deselected.
    """
    # Signal emitted with list of selected QIDs whenever selection changes
    selection_changed = pyqtSignal(list)
    
    def __init__(self, placeholder_text="Type to search (e.g., 'Eiffel Tower')...", 
                 title="Wikidata Entities:", parent=None):
        super().__init__(parent)
        
        # Store selected entities
        self.selected_entities = []
        
        # Search thread
        self.search_thread = WikidataSearcher()
        self.search_thread.results_found.connect(self.on_search_results)
        
        # Debounce timer
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(400)
        self.debounce_timer.timeout.connect(self.start_search)
        
        self.initUI(placeholder_text, title)
    
    def initUI(self, placeholder_text, title):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Title label
        self.title_label = QLabel(f"<b>{title}</b>")
        layout.addWidget(self.title_label)
        
        # Search Input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(placeholder_text)
        self.search_input.textChanged.connect(self.on_text_changed)
        layout.addWidget(self.search_input)
        
        # Suggestions List (Hidden by default)
        self.suggestions_list = QListWidget()
        self.suggestions_list.setVisible(False)
        self.suggestions_list.setMinimumHeight(150)
        self.suggestions_list.setMaximumHeight(150)
        self.suggestions_list.itemClicked.connect(self.add_entity_from_suggestion)
        layout.addWidget(self.suggestions_list)
        
        # Selected Entities List
        self.selected_list_widget = QListWidget()
        self.selected_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.selected_list_widget.setStyleSheet("""
            QListWidget {
                background-color: #edf8b1;
                border: 1px solid #ccc;
                border-radius: 4px;
                min-height: 50px;
                max-height: 150px;
            }
            QListWidget::item {
                border-bottom: 1px solid #e0e0e0;
                padding: 5px;
            }
        """)
        layout.addWidget(self.selected_list_widget)
        
        self.setLayout(layout)
    
    def on_text_changed(self, text):
        if len(text.strip()) < 2:
            self.suggestions_list.hide()
            self.debounce_timer.stop()
            return
        self.debounce_timer.start()
    
    def start_search(self):
        query = self.search_input.text().strip()
        if query:
            self.suggestions_list.clear()
            self.search_thread.search(query)
    
    def on_search_results(self, results):
        self.suggestions_list.clear()
        
        if not results:
            self.suggestions_list.hide()
            return
        
        self.suggestions_list.setVisible(True)
        for item in results:
            label = item.get('label', 'No Label')
            qid = item.get('id')
            desc = item.get('description', 'No description available')
            
            display_text = f"{label} ({qid})\t   ↳ {desc}"
            
            list_item = QListWidgetItem(display_text)
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.suggestions_list.addItem(list_item)
    
    def add_entity_from_suggestion(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        qid = data.get('id')
        
        # Prevent duplicates
        if any(e['id'] == qid for e in self.selected_entities):
            self.suggestions_list.hide()
            self.search_input.clear()
            return
        
        self.selected_entities.append(data)
        self.add_selected_item_widget(data)
        
        # Reset Search
        self.search_input.clear()
        self.suggestions_list.hide()
        
        # Emit selection changed signal
        self.selection_changed.emit(self.get_selected_qids())
    
    def add_selected_item_widget(self, data):
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
        
        widget_item = QListWidgetItem(self.selected_list_widget)
        widget_item.setSizeHint(widget.sizeHint())
        self.selected_list_widget.setItemWidget(widget_item, widget)
    
    def remove_entity(self, qid, widget_item):
        self.selected_entities = [e for e in self.selected_entities if e['id'] != qid]
        
        row = self.selected_list_widget.row(widget_item)
        self.selected_list_widget.takeItem(row)
        
        # Emit selection changed signal
        self.selection_changed.emit(self.get_selected_qids())
    
    def get_selected_qids(self):
        """Returns list of QIDs for use in SDC upload"""
        return [e['id'] for e in self.selected_entities]
    
    def get_selected_entities(self):
        """Returns the full selected entities data"""
        return self.selected_entities.copy()
    
    def clear_selection(self):
        """Clear all selected entities"""
        self.selected_list_widget.clear()
        self.selected_entities.clear()
        self.selection_changed.emit([])