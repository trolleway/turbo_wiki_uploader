
from exif import Image as ExifImage
import mwclient
import tempfile
import requests
import os

class ExifReader:
    @staticmethod
    def get_exif_data(file_path):
    
        with open(file_path, 'rb') as image_file:
            exif_img = ExifImage(image_file)
  
    
        """Extracts lat, lon, and heading (azimuth) from EXIF."""
        lat, lon, heading, dt_iso = None, None, None, None

        def dms_to_decimal(dms, ref):
            degrees, minutes, seconds = dms
            decimal = degrees + minutes / 60 + seconds / 3600
            if ref in ['S', 'W']:
                decimal = -decimal
            return decimal

        try:
            if hasattr(exif_img, 'gps_latitude') and hasattr(exif_img, 'gps_longitude'):
                lat = dms_to_decimal(exif_img.gps_latitude, exif_img.gps_latitude_ref)
                lon = dms_to_decimal(exif_img.gps_longitude, exif_img.gps_longitude_ref)
            
            if hasattr(exif_img, 'gps_img_direction'):
                heading = float(exif_img.gps_img_direction)
                
            if hasattr(exif_img, 'datetime_original'):
                # EXIF format is usually "YYYY:MM:DD HH:MM:SS"
                exif_dt = exif_img.datetime_original
                if exif_dt and len(exif_dt) >= 19:
                    date_part, time_part = exif_dt[:10], exif_dt[11:19]
                    # Convert colons in date to dashes for ISO format
                    iso_date = date_part.replace(':', '-')
                    dt_iso = f"{iso_date}T{time_part}"
                
        except AttributeError:
            pass

        res={'lat':lat,'lon':lon,'heading':heading,'dt_iso':dt_iso}
        return res

    def download_wikimedia_file(self,file_title):
        """Fetches Wikimedia file info and downloads it to a temporary folder."""
        # Ensure the title has the correct prefix
        if not file_title.startswith("File:"):
            file_title = "File:" + file_title

        # Wikimedia API endpoint
        API_URL = "https://wikimedia.org"

        # Parameters to get file information
        params = {
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "titles": file_title,
            "iiprop": "url|size|mime",
        }

        try:
            # 1. Fetch file information from the API
            response = requests.get(API_URL, params=params)
            response.raise_for_status()
            data = response.json()

            # Extract page information
            pages = data.get("query", {}).get("pages", {})
            page_id = list(pages.keys())[0]

            if page_id == "-1":
                print(f"Error: File '{file_title}' not found on Wikimedia Commons.")
                return None

            # Extract file details and download URL
            image_info = pages[page_id]["imageinfo"][0]
            download_url = image_info["url"]
            file_name = image_info["descriptionurl"].split("/")[-1]

            print(f"File found: {file_name}")
            print(f"Original URL: {download_url}")

            # 2. Download the file to a temporary folder
            # Get the system's standard temporary directory path
            temp_dir = tempfile.gettempdir()
            download_path = os.path.join(temp_dir, file_name)

            print(f"Downloading to temporary folder...")
            file_response = requests.get(download_url, stream=True)
            file_response.raise_for_status()

            # Write the file in chunks to handle large files efficiently
            with open(download_path, "wb") as f:
                for chunk in file_response.iter_content(chunk_size=8192):
                    f.write(chunk)

            print(f"Success! File downloaded to: {download_path}")
            return download_path

        except requests.exceptions.RequestException as e:
            print(f"Network or API error: {e}")
            return None