# search-arxiv.py
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import csv
import time
import re

POPULATION_TERMS = 'ADHD AND autis* OR ASD OR AuDHD' # When I change it back to AND it gets only three results if it's OR it gets 100+ results
INTERVENTION_TERMS = 'app OR mobile application OR mHealth OR eHealth OR digital tool OR web-based OR software OR digital therapeutics'
AGE_TERMS = 'adult OR adolescen* OR young people OR "16+" OR university student OR high school student'

SEARCH_QUERY = f'( (ti:{POPULATION_TERMS} OR abs:{POPULATION_TERMS}) AND (ti:{INTERVENTION_TERMS} OR abs:{INTERVENTION_TERMS}) AND (ti:{AGE_TERMS} OR abs:{AGE_TERMS}) )'

BASE_URL = 'http://export.arxiv.org/api/query?'
OUTPUT_CSV = 'arxiv_results.csv'
MAX_RESULTS_PER_PAGE = 100
WAIT_TIME = 5 

ATOM_NAMESPACE = {'atom': 'http://www.w3.org/2005/Atom'}


def fetch_results(search_query, start=0, max_results=100):
    query_params = {
        'search_query': search_query,
        'start': start,
        'max_results': max_results,
        'sortBy': 'submittedDate', # Or 'lastUpdatedDate', 'relevance'
        'sortOrder': 'descending'
    }
    encoded_params = urllib.parse.urlencode(query_params)
    url = BASE_URL + encoded_params
    print(f"Fetching: {url}") # Log the URL being fetched

    try:
        with urllib.request.urlopen(url) as response:
            if response.status == 200:
                return response.read()
            else:
                print(f"Error fetching results: HTTP Status {response.status}")
                return None
    except urllib.error.URLError as e:
        print(f"Error fetching results: {e}")
        return None

def parse_entry(entry):
    
    data = {}
    try:
        # Extract arXiv ID from the <id> URL (e.g., http://arxiv.org/abs/1706.03762v5 -> 1706.03762)
        id_url = entry.find('atom:id', ATOM_NAMESPACE).text
        match = re.search(r'arxiv.org/abs/([^v]+)', id_url)
        data['arxiv_id'] = match.group(1) if match else id_url # Fallback to full URL if pattern fails

        data['updated'] = entry.find('atom:updated', ATOM_NAMESPACE).text
        data['published'] = entry.find('atom:published', ATOM_NAMESPACE).text
        data['title'] = entry.find('atom:title', ATOM_NAMESPACE).text.strip().replace('\n', ' ').replace('  ', ' ') # Clean title
        data['summary'] = entry.find('atom:summary', ATOM_NAMESPACE).text.strip().replace('\n', ' ').replace('  ', ' ') # Clean summary

        # Concatenate author names
        authors = entry.findall('atom:author', ATOM_NAMESPACE)
        data['authors'] = '; '.join([author.find('atom:name', ATOM_NAMESPACE).text for author in authors])

        # Extract links
        data['link_abstract'] = ''
        data['link_pdf'] = ''
        links = entry.findall('atom:link', ATOM_NAMESPACE)
        for link in links:
            if link.get('rel') == 'alternate' and link.get('type') == 'text/html':
                data['link_abstract'] = link.get('href')
            elif link.get('title') == 'pdf' and link.get('type') == 'application/pdf':
                data['link_pdf'] = link.get('href')
        # Fallback if specific types aren't found but rel=alternate exists
        if not data['link_abstract']:
             for link in links:
                 if link.get('rel') == 'alternate':
                     data['link_abstract'] = link.get('href')
                     break # Take the first alternate link
        # Fallback for PDF link if title='pdf' isn't found
        if not data['link_pdf']:
             for link in links:
                 if link.get('href', '').endswith('.pdf'):
                     data['link_pdf'] = link.get('href')
                     break # Take the first link ending in .pdf

    except AttributeError as e:
        print(f"Error parsing entry element: {e}. Skipping entry.")
        title_element = entry.find('atom:title', ATOM_NAMESPACE)
        entry_title = title_element.text if title_element is not None else "Unknown Title"
        print(f"Problematic entry title (if available): {entry_title}")
        return None 
    return data

def save_to_csv(data_list, filename):
    if not data_list:
        print("No data to save.")
        return

    headers = ['arxiv_id', 'updated', 'published', 'title', 'summary', 'authors', 'link_abstract', 'link_pdf']
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            writer.writerows(data_list)
        print(f"Successfully saved {len(data_list)} results to {filename}")
    except IOError as e:
        print(f"Error writing to CSV file {filename}: {e}")


if __name__ == "__main__":
    all_results = []
    start_index = 0
    total_results_processed = 0

    while True:
        print(f"\nRequesting results starting from index {start_index}...")
        xml_data = fetch_results(SEARCH_QUERY, start=start_index, max_results=MAX_RESULTS_PER_PAGE)

        if not xml_data:
            print("Failed to fetch data or no more results. Stopping.")
            break

        try:
            root = ET.fromstring(xml_data)
            entries = root.findall('atom:entry', ATOM_NAMESPACE)

            if not entries:
                print("No more entries found in the response.")
                break

            print(f"Found {len(entries)} entries in this batch.")
            batch_results = []
            for entry in entries:
                parsed_data = parse_entry(entry)
                if parsed_data:
                    batch_results.append(parsed_data)

            all_results.extend(batch_results)
            total_results_processed += len(batch_results) 

            
            if len(entries) < MAX_RESULTS_PER_PAGE:
                print("Received fewer results than max_results, assuming end of results.")
                break

            start_index += len(entries) 

            print(f"Waiting {WAIT_TIME} seconds before next request...")
            time.sleep(WAIT_TIME)

        except ET.ParseError as e:
            print(f"Error parsing XML: {e}")
            break
        except Exception as e:
            print(f"An unexpected error occurred during processing: {e}")
            break

    if all_results:
        save_to_csv(all_results, OUTPUT_CSV)
    else:
        print("No results were successfully processed or saved.")

    print(f"\nFinished processing. Total results saved: {len(all_results)}")
