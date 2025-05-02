import os
import glob
import logging
import sys
import json
from paperscraper.xrxiv.xrxiv_query import XRXivQuery
import tempfile

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)

population_group = ["ADHD", "autis*", "ASD", "AuDHD"]
intervention_group = ["app", "mobile application", "mHealth", "eHealth", "digital tool", "web-based", "software", "digital therapeutics"]
age_group = ["adult", "adolescen*", "young people", "16+", "university student", "high school student"]

search_query = [population_group, intervention_group, age_group]
final_output_filename = 'medrxiv_results.jsonl'

dump_dir = 'server_dumps'
dump_pattern = os.path.join(dump_dir, 'medrxiv_*.jsonl')
dump_files = glob.glob(dump_pattern)

if not dump_files:
    try:
        import paperscraper
        pkg_path = os.path.dirname(paperscraper.__file__)
        dump_dir = os.path.join(pkg_path, 'server_dumps')
        dump_pattern = os.path.join(dump_dir, 'medrxiv_*.jsonl')
        dump_files = glob.glob(dump_pattern)
    except ImportError:
        pkg_path = None

if not dump_files:
    logging.error(f"Could not find medRxiv dump file matching '{dump_pattern}'.")
    logging.error("Please ensure the dump was downloaded successfully.")
    sys.exit(1)

# Use the most recently created dump file
latest_dump_file = max(dump_files, key=os.path.getctime)
logging.info(f"Using medRxiv dump file: {latest_dump_file}")

# --- Perform Search and Handle Deduplication ---
try:
    logging.info(f"Initializing XRXivQuery with dump file: {latest_dump_file}")
    querier = XRXivQuery(latest_dump_file)
    
    logging.info(f"Performing keyword search with query: {json.dumps(search_query)}")
    
    # Create a temporary file for initial search results
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.jsonl') as temp_file:
        temp_filename = temp_file.name
        logging.info(f"Created temporary file: {temp_filename}")
    
    # Search and write to temporary file
    querier.search_keywords(search_query, output_filepath=temp_filename)
    
    # Read the temporary file to perform deduplication
    logging.info(f"Reading results from temporary file for deduplication")
    results = []
    with open(temp_filename, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                result = json.loads(line.strip())
                results.append(result)
            except json.JSONDecodeError:
                logging.warning(f"Skipping invalid JSON line: {line[:100]}...")
    
    logging.info(f"Initial search found {len(results)} results.")
    
    # Deduplicate results
    seen_keys = set()
    unique_results = []
    
    for result in results:
        # Get DOI (primary deduplication key)
        doi = result.get('doi')
        if doi:
            doi_key = f"doi:{doi.lower()}"
            if doi_key not in seen_keys:
                seen_keys.add(doi_key)
                unique_results.append(result)
            else:
                logging.debug(f"Skipping duplicate DOI: {doi}")
        else:
            # If no DOI, use title for deduplication
            title = result.get('title')
            if title:
                title_key = f"title:{title.lower()}"
                if title_key not in seen_keys:
                    seen_keys.add(title_key)
                    unique_results.append(result)
                else:
                    logging.debug(f"Skipping duplicate title: {title}")
            else:
                # No DOI or title, use whatever unique identifier we can find
                id_value = result.get('id') or result.get('_id') or str(result)
                id_key = f"id:{id_value}"
                if id_key not in seen_keys:
                    seen_keys.add(id_key)
                    unique_results.append(result)
                else:
                    logging.debug(f"Skipping duplicate with id: {id_value}")
    
    logging.info(f"Found {len(unique_results)} unique results after deduplication (removed {len(results) - len(unique_results)} duplicates).")
    
    # Write deduplicated results to final file
    with open(final_output_filename, 'w', encoding='utf-8') as f:
        for result in unique_results:
            f.write(json.dumps(result) + '\n')
    
    logging.info(f"Deduplicated results saved to {final_output_filename}")
    
    # Clean up temporary file
    if os.path.exists(temp_filename):
        os.remove(temp_filename)
        logging.info(f"Removed temporary file: {temp_filename}")

except FileNotFoundError:
    logging.error(f"Error: The specified dump file was not found: {latest_dump_file}")
    sys.exit(1)
except Exception as e:
    logging.error(f"An error occurred during the search process: {e}", exc_info=True)
    sys.exit(1)

logging.info("Script finished successfully.")
sys.exit(0)
