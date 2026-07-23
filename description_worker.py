
from PyQt6.QtCore import QThread, pyqtSignal
from exif_helper import ExifReader
import os

import requests
from string import Template


class DescriptionGenerationThread(QThread):
    """
    Background thread to extract EXIF and generate 
    the Wikitext template without freezing the UI.
    """
    description_generated = pyqtSignal(dict)
    log_signal = pyqtSignal(str)



    def __init__(self, file_path, username,wikidata_ids,location_wikidata_ids,USERAGENT,preset='place',preset_fields={},camera_location_lat=None,camera_location_lon=None):
        super().__init__()
        self.file_path = file_path
        self.username = username
        self.wikidata_ids=wikidata_ids
        self.location_wikidata_ids=location_wikidata_ids
        self.USERAGENT = USERAGENT
        self.preset = preset
        self.preset_fields = preset_fields
        self.camera_location_lat=camera_location_lat
        self.camera_location_lon=camera_location_lon


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

        if 'commonswiki' in wdobj.get('sitelinks',{}):
            if 'ategory:' in wdobj['sitelinks']['commonswiki']['title']:
                return wdobj['sitelinks']['commonswiki']['title']
        if 'P373' in wdobj.get('claims',{}):
            return 'Category:'+wdobj['claims']['P373'][0]['mainsnak']['datavalue']['value']
        return None
    

    def run(self):
        from datetime import datetime
        try:
            if not self.file_path:
                return

            
            wdobj_dict=dict()
            for wikidata_id in self.wikidata_ids:
                wdobj_dict[wikidata_id] = self.get_wikidata_object(wikidata_id)
                
            
            location_wdobj = self.get_wikidata_object(self.location_wikidata_ids[0])
            description_failed=False    
            if 'en' not in location_wdobj['labels']:
                self.log_signal.emit(f"Error: please add english label to https://www.wikidata.org/wiki/{location_wdobj['id']}")
                description_failed = True
            for wdobj in wdobj_dict.values():
                if 'en' not in wdobj['labels']:
                    self.log_signal.emit(f"Error: please add english label to https://www.wikidata.org/wiki/{wdobj['id']}")
                    description_failed = True
                
            if description_failed:
                return
            
            # descriptions presets
            # now all presets implemented in this method, to make more simple code
            
            self.log_signal.emit(self.preset)
            
            exif_helper = ExifReader()
            exifdata = exif_helper.get_exif_data(self.file_path)
            try:
                timestamp = exifdata['dt_iso']
                timestamp2 = datetime.fromisoformat(timestamp).strftime('%Y%m%d_%H%M%S')
            except:
                self.log_signal.emit(f"Error: while reading datetime. The image must have datetime in EXIF")
            ext = os.path.splitext(self.file_path)[1]
            
            if self.preset=='place':
                #categories
                categories=list()
                categories_text=''
                category_for_location_needed = True
                for wdobj in wdobj_dict.values():
                    categories.append(self.wdobj_category(wdobj))
        
                categories.append(self.wdobj_category(location_wdobj) )
                categories = [x for x in categories if x is not None]
                categories = [f"[[{item}]]\n" for item in categories]
                categories = list(set(categories))
                
                if len(categories)>0:
                    categories_text="\n".join(categories)
                    
                ls=list()
                for wikidata_id in self.wikidata_ids:
                    ls.append(wdobj_dict[wikidata_id]['labels']['en']['value'])    
                if location_wdobj['labels']['en']['value'] in ls:
                    l=''
                else:
                    l=location_wdobj['labels']['en']['value']
                    
                commons_filename = l + ' ' + ls[0]+' '+timestamp2+ext
                commons_filename = commons_filename.strip()

                short_description = ' '.join(ls) + ' ' + l
                

            
            elif self.preset=='thing_in_place':
            
                #categories
                categories=list()
                categories_text=''
                category_for_location_needed = True
                for wdobj in wdobj_dict.values():
                    #categories.append(self.wdobj_category(wdobj))
                    category = self.get_category_for_object_in_location(wdobj,location_wdobj)
                    if category is None:
                        category = self.wdobj_category(wdobj)
                    
                    
                    self.log_signal.emit(category)
                    if category is not None:
                        if 'Category:' not in category:
                            category = 'Category:'+category
                        categories.append(category)
                        category_for_location_needed = False
                if category_for_location_needed:        
                    categories.append(self.wdobj_category(location_wdobj) )
                categories = [x for x in categories if x is not None]
                categories = [f"[[{item}]]\n" for item in categories]
                categories = list(set(categories))
                
                if len(categories)>0:
                    categories_text="\n".join(categories)      

                
                objectname = self.preset_fields.get('objectname','')
                
                ls=list()
                for wikidata_id in self.wikidata_ids:
                    ls.append(wdobj_dict[wikidata_id]['labels']['en']['value'])    
                if location_wdobj['labels']['en']['value'] in ls:
                    locname=''
                else:
                    locname=location_wdobj['labels']['en']['value']

                    
                if objectname != '':
                    commons_filename = f"{locname} {objectname} {timestamp2}{ext}"
                    short_description = objectname + ' ' + locname
                else:
                    commons_filename = f"{locname} {ls[0]} {timestamp2}{ext}"
                    short_description = ' '.join(ls) + ' ' + locname
                commons_filename = commons_filename.strip()

            
            

            
            if not self.camera_location_lat or not self.camera_location_lon:
                self.log_signal.emit(f"Error: please set camera location coordinates")
                description_failed = True
            
            if description_failed:
                return
            

                


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
{{{{Location dec|{self.camera_location_lat}|{self.camera_location_lon}}}}}

=={{{{int:license-header}}}}==
{{{{self|cc-by-4.0}}}}

[[Category:Uploaded with Turbo Wiki Uploader]]
[[Category:Photographs by {self.username}]]
{categories_text}
"""


            
            description_dict={'commons_filename':commons_filename,'description':description,'short_description':short_description}
            self.description_generated.emit(description_dict)

        except Exception as e:
            self.log_signal.emit(f"Error generating description: {str(e)}")
            



    def search_commonscat_by_2_wikidata(self,subject_id: str, country_id: str) -> dict:
        """Executes a SPARQL query on Wikidata using subject and country entity IDs.

        Args:
            subject_id: The Wikidata entity ID for the subject (e.g., 'Q146')
            country_id: The Wikidata entity ID for the country (e.g., 'Q30')

        Returns:
            A dictionary containing the JSON response bindings from Wikidata.
        """
        # 1. Define the SPARQL endpoint URL
        url = "https://query.wikidata.org/sparql"

        # 2. Set up the template query string
        query_template = Template(
            """SELECT ?item ?itemLabel ?commonsCategory ?sitelink WHERE {
  ?item wdt:P971 wd:$subject .
  ?item wdt:P971 wd:$country .
  
  # Selects P373 (Wikimedia Commons category text string)
  OPTIONAL { ?item wdt:P373 ?commonsCategory. }
  
  # Selects the formal Wikimedia Commons category sitelink URL
  OPTIONAL {
    ?sitelink schema:about ?item ;
              schema:isPartOf <https://commons.wikimedia.org/> .
  }
  
  SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }
}"""

        )

        # 3. Substitute placeholders with the provided parameters
        # Note: "[auto_language]" changed to "[style_language],en" for API compatibility
        sparql_query = query_template.substitute(
            subject=subject_id, country=country_id
        )

        # 4. Configure headers (Wikidata requires a specific User-Agent)
        headers = {
            "User-Agent": self.USERAGENT,
            "Accept": "application/sparql-results+json",
        }
        


        # 5. Execute the HTTP GET request

        response = requests.get(
            url, params={"query": sparql_query, "format": "json"}, headers=headers
        )

        # 6. Raise an exception for HTTP error codes
        response.raise_for_status()

        # 7. Extract and return the inner data list
        data = response.json()
        if data['results']['bindings']==[]:
            return None
        sitelink_category=data.get("results", {}).get("bindings", [])[0].get("sitelink",{}).get("value",'').replace('https://commons.wikimedia.org/wiki/Category:','')
        P373_category=data.get("results", {}).get("bindings", [])[0].get("commonsCategory",{}).get("value",'')

        return sitelink_category if sitelink_category is not None else P373_category
    
    def get_upper_location_wdid(self,location_wdobj):
        has_claims = False
        try:
            v=location_wdobj['claims']['P131'][0]['mainsnak']['datavalue']['value']['id']
            has_claims=True
        except:
            return None
        #get prefered or not depracated or frist claim P131
        if has_claims == False:
            return None
        
        ranks = list()
        for claim in location_wdobj['claims']['P131']:
            rank = claim['rank']
            if rank=='preferred':
                return claim['mainsnak']['datavalue']['value']['id']
        
        for claim in location_wdobj['claims']['P131']:
            rank = claim['rank']        
            if rank=='normal':
                return claim['mainsnak']['datavalue']['value']['id']
            
           
            
    def is_category_exists(self,category_name) -> bool:  
        api_url = "https://commons.wikimedia.org/w/api.php"
        headers = {
            "User-Agent": self.USERAGENT
        }
        params = {
            "action": "query",
            "format": "json",
            "titles": f"Category:{category_name}"
        }

        try:
            response = requests.get(api_url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Extract pages from the response
            pages = data.get("query", {}).get("pages", {})
            
            # MediaWiki returns a page ID of "-1" if the page/category does not exist
            for page_id in pages.keys():
                if int(page_id) > 0:
                    return True
                    
            return False
            
        except requests.exceptions.RequestException as e:
            print(f"API Request failed: {e}")
            return False


        
    def get_category_for_object_in_location(self, object_wdobj, location_wdobj):
        stop_hieraechy_walk = False
        cnt = 0
        while not stop_hieraechy_walk:
            cnt = cnt + 1
            if cnt > 9:
                stop_hieraechy_walk = True
            object_name = self.wdobj_category(object_wdobj).replace('Category:','')
            lc=self.wdobj_category(location_wdobj)
            if lc is None: lc=''
            location_name = lc.replace('Category:','')
            msg = f"Search Wikidata for category combines topics 〚{object_wdobj.get('labels',{}).get('en',{}).get('value','')}〛〚{location_wdobj.get('labels',{}).get('en',{}).get('value','')}〛"
            self.log_signal.emit(msg)
            #print(msg)
            category = self.search_commonscat_by_2_wikidata(object_wdobj['id'],location_wdobj['id'])
            if category is not None: 
                return category
            suggested_category = f'{object_name} in {location_name}'
            msg=f'Check if exists [[Category:{suggested_category}]]'
            self.log_signal.emit(msg)
            #print(msg)
            if self.is_category_exists(suggested_category):
                return suggested_category
            
            upper_wdid=self.get_upper_location_wdid(location_wdobj)
            if upper_wdid is None:
                return None
            upper_wdobj = self.get_wikidata_object(upper_wdid)
            location_wdobj = upper_wdobj