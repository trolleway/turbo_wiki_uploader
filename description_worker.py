
from PyQt6.QtCore import QThread, pyqtSignal
from exif_helper import ExifReader
import os

import requests

class DescriptionGenerationThread(QThread):
    """
    Background thread to extract EXIF and generate 
    the Wikitext template without freezing the UI.
    """
    description_generated = pyqtSignal(dict)
    log_signal = pyqtSignal(str)
    USERAGENT = 'TurboWikiUploader/1.0  (trolleway@yandex.ru)'


    def __init__(self, file_path, username,wikidata_ids,location_wikidata_ids):
        super().__init__()
        self.file_path = file_path
        self.username = username
        self.wikidata_ids=wikidata_ids
        self.location_wikidata_ids=location_wikidata_ids


    def get_wikidata_object(self,entity_id):
        """Retrieves both labels and claims for a given Wikidata ID.

        Args:
            entity_id (str): The Wikidata ID (e.g., 'Q42').

        Returns:
            dict: A dictionary containing 'labels', 'claims', or 'error'.
        """
        url = "https://www.wikidata.org/w/api.php"

        # Requested both 'labels' and 'claims' separated by a pipe
        params = {
            "action": "wbgetentities",
            "ids": entity_id,
            "props": "labels|claims|sitelinks",
            "format": "json",
        }

        headers = {"User-Agent": self.USERAGENT}

        try:
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            entity = data.get("entities", {}).get(entity_id, {})

            if "missing" in entity:
                return {"error": f"Entity '{entity_id}' not found"}

            # Extract and format labels (all languages)
            return entity

        except requests.exceptions.RequestException as e:
            return {"error": f"API Request failed: {e}"}

    def wdobj_category(self,wdobj):
        if 'commonswiki' in wdobj['sitelinks']:
            return wdobj['sitelinks']['commonswiki']['title']
        if 'P373' in wdobj['claims']:
            return 'Category:'+wdobj['claims']['P373'][0]['mainsnak']['datavalue']['value']
        return None
    

    def run(self):
        try:
            if not self.file_path:
                return

            
            wdobj_dict=dict()
            for wikidata_id in self.wikidata_ids:
                wdobj_dict[wikidata_id] = self.get_wikidata_object(wikidata_id)
                
            
            location_wdobj = self.get_wikidata_object(self.location_wikidata_ids[0])
            description_failed=False    
            if 'en' not in location_wdobj['labels']:
                self.log_signal.emit(f"Error: please add english name to https://www.wikidata.org/wiki/{location_wdobj['id']}")
                description_failed = True
            for wdobj in wdobj_dict.values():
                if 'en' not in wdobj['labels']:
                    self.log_signal.emit(f"Error: please add english name to https://www.wikidata.org/wiki/{wdobj['id']}")
                    description_failed = True
                
            if description_failed:
                return
            
            #categories
            categories=list()
            categories_text=''
            for wdobj in wdobj_dict.values():
                categories.append(self.wdobj_category(wdobj))
            categories.append(self.wdobj_category(location_wdobj) )
            categories = [x for x in categories if x is not None]
            categories = [f"[[{item}]]\n" for item in categories]
            
            if len(categories)>0:
                categories_text="\n".join(categories)
            
            
            
            exif_helper = ExifReader()
            exifdata = exif_helper.get_exif_data(self.file_path)
            timestamp = exifdata['dt_iso']
            from datetime import datetime
            timestamp2 = datetime.fromisoformat(timestamp).strftime('%Y%m%d_%H%M%S')
            ext = os.path.splitext(self.file_path)[1]
            

                
            str_heading = ''
            if exifdata['heading'] is not None:
                str_heading = f"|heading:{exifdata['heading']}"

            description = f"""=={{{{int:filedesc}}}}==
{{{{Information
|other_fields_1 =
{{{{Information field
 |name  = {{{{Label|P1071|link=-|capitalization=ucfirst}}}}
 |value = {{{{#invoke:Information|SDC_Location|icon=true}}}} {{{{#if:{{{{#property:P1071|from=M{{{{PAGEID}}}} }}}}}}|(<small>{{{{#invoke:PropertyChain|PropertyChain|qID={{{{#invoke:WikidataIB |followQid |props=P1071}}}}|pID=P131|endpID=P17}}}}</small>)}}}} }}}}
{{{{Information field
 |name  = {{{{Label|P180|link=-|capitalization=ucfirst}}}}
 |value = {{{{#property:P180|from=M{{{{PAGEID}}}} }}}} }}}}
|source={{{{Own work}}}}  
|date={{{{Taken on|{exifdata['dt_iso']}|source=EXIF}}}}
|author=[[User:{self.username}|{self.username}]]
}}}}
{{{{Location dec|{exifdata['lat']}|{exifdata['lon']}{str_heading}}}}}

=={{{{int:license-header}}}}==
{{{{self|cc-by-4.0}}}}

[[Category:Uploaded with Turbo Wiki Uploader]]
[[Category:Photographs by {self.username}]]
{categories_text}
"""

            ls=list()
            for wikidata_id in self.wikidata_ids:
                ls.append(wdobj_dict[wikidata_id]['labels']['en']['value'])    

            commons_filename = location_wdobj['labels']['en']['value'] + ' ' + ls[0]+' '+timestamp2+ext
            short_description = ' '.join(ls) + ' ' + location_wdobj['labels']['en']['value']
            
            #short_description = 'short_description'
            
            
            
            description_dict={'commons_filename':commons_filename,'description':description,'short_description':short_description}
            self.description_generated.emit(description_dict)

        except Exception as e:
            self.log_signal.emit(f"Error generating description: {str(e)}")