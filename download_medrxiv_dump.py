import logging
import sys
from paperscraper.get_dumps import medrxiv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)

try:
    logging.info("Starting medRxiv dump download. This may take around 30 minutes...")
    medrxiv(max_retries=20)
    logging.info("medRxiv dump download process finished.")

except Exception as e:
    logging.error(f"An error occurred during medRxiv dump download: {e}", exc_info=True)
    sys.exit(1)

logging.info("Script finished.")
sys.exit(0)
