
from PyQt6.QtCore import QThread, pyqtSignal
from exif_helper import ExifReader

class DescriptionGenerationThread(QThread):
    """
    Background thread to extract EXIF and generate 
    the Wikitext template without freezing the UI.
    """
    description_generated = pyqtSignal(str)
    log_signal = pyqtSignal(str)

    def __init__(self, file_path, username):
        super().__init__()
        self.file_path = file_path
        self.username = username

    def run(self):
        try:
            if not self.file_path:
                return

            exif_helper = ExifReader()
            exifdata = exif_helper.get_exif_data(self.file_path)
            
            if exifdata['lat'] and exifdata['lon']:
                self.log_signal.emit(f"Coords: {exifdata['lat']:.4f}, {exifdata['lon']:.4f}.")
                
            str_heading = ''
            if exifdata['heading'] is not None:
                str_heading = f"|heading:{exifdata['heading']}"

            description = f"""== {{int:filedesc}} ==
{{{{Information
|other_fields_1 =
{{{{Information field

 |name  = {{{{Label|P1071|link=-|capitalization=ucfirst}}}}
 |value = {{{{#invoke:Information|SDC_Location|icon=true}}}} {{{{#if:{{{{#property:P1071|from=M{{{{PAGEID}}}} }}}}}}|(<small>{{{{#invoke:PropertyChain|PropertyChain|qID={{{{#invoke:WikidataIB |followQid |props=P1071}}}}|pID=P131|endpID=P17}}}}</small>)}}}} }}}}
{{{{Information field

 |name  = {{{{Label|P180|link=-|capitalization=ucfirst}}}}
 |value = {{{{#property:P180|from=M{{{{PAGEID}}}} }}}} }}}} 
|date={{{{Taken on|{exifdata['dt_iso']}|source=EXIF}}}}
|author=[[User:{self.username}|{self.username}]]
}}}}
{{{{Location dec|{exifdata['lat']}|{exifdata['lon']}{str_heading}}}}}

== {{int:license-header}} ==
{{{{self|cc-by-4.0}}}}

[[Category:Uploaded with Turbo Wiki Uploader]]
[[Category:Photographs by {self.username}]]"""

            self.description_generated.emit(description)

        except Exception as e:
            self.log_signal.emit(f"Error generating description: {str(e)}")