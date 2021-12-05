
import logging
import json
import requests
import pandas as pd
from tqdm import tqdm

class Scraper:
    """
    scrape wahl
    """

    def __init__(self):
        self.url = "https://neuwal.com/wahlumfragen/data/neuwal-wahlumfragen-user.json"
    
    def load(self):
        logging.info("Loading data...")
        try:
            response = requests.get(self.url)
        except Exception as err:
            logging.error(f"Error while trying to read data: {err}")
            return False
        if response.status_code == 200:
            logging.info(f"Status OK")
            dictionary = json.loads(response.text)["data"]
            df = pd.DataFrame(dictionary)
            logging.info(f"Data loaded")
            return df
        else:
            logging.error(f'Something went wrong: {response.status_code}')
            return None
            

if __name__ == "__main__":
    scraper = Scraper()
    dictionary, df = scraper.load()