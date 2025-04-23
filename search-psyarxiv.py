#!/usr/bin/env python3
"""
search-psyarxiv.py - An improved script to search for ADHD/autism digital intervention papers on PsyArXiv
with better CSV formatting
"""

import requests
import csv
import time
import sys
import json
import re
from datetime import datetime

POPULATION_TERMS = ['adhd', 'attention deficit', 'autis', 'asd', 'audhd']
INTERVENTION_TERMS = ['app', 'mobile application', 'mhealth', 'ehealth', 
                     'digital tool', 'web-based', 'software', 'digital therapeutic']
AGE_TERMS = ['adult', 'adolescen', 'young people', '16+', 
            'university student', 'high school student']

BASE_URL = 'https://api.osf.io/v2/preprints/'
PROVIDER = 'psyarxiv'  # Specific provider for PsyArXiv
OUTPUT_CSV = 'psyarxiv_results_clean.csv'
MAX_RESULTS_PER_PAGE = 100  
MAX_PAGES = 20  
WAIT_TIME = 1  


def fetch_results(page=1):
    params = {
        'page': page,
        'filter[provider]': PROVIDER,
        'page[size]': MAX_RESULTS_PER_PAGE
    }
    url = BASE_URL
    print(f"Fetching: {url} with params: {params}")  # Log the URL being fetched
    
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching results: HTTP Status {response.status_code}")
            print(f"Response: {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching results: {e}")
        return None

def passes_filter_criteria(preprint):
    title = preprint.get('attributes', {}).get('title', '').lower()
    description = preprint.get('attributes', {}).get('description', '').lower()
    tags = [tag.lower() for tag in preprint.get('attributes', {}).get('tags', [])]
    
    search_text = f"{title} {description} {' '.join(tags)}"
    
    display_title = title[:75] + "..." if len(title) > 75 else title
    print(f"Examining: {display_title}")
    
    # Track matching terms for better reporting
    matching_pop_terms = []
    matching_int_terms = []
    matching_age_terms = []
    
    for term in POPULATION_TERMS:
        if term in search_text:
            matching_pop_terms.append(term)
    
    has_population = len(matching_pop_terms) > 0
    if has_population:
        print(f"  ✓ Population terms found: {', '.join(matching_pop_terms)}")
    else:
        print("  ✗ No population terms found")
        return False
        
    for term in INTERVENTION_TERMS:
        if term in search_text:
            matching_int_terms.append(term)
    
    has_intervention = len(matching_int_terms) > 0
    if has_intervention:
        print(f"  ✓ Intervention terms found: {', '.join(matching_int_terms)}")
    else:
        print("  ✗ No intervention terms found")
        return False
        
    for term in AGE_TERMS:
        if term in search_text:
            matching_age_terms.append(term)
    
    has_age = len(matching_age_terms) > 0
    if has_age:
        print(f"  ✓ Age terms found: {', '.join(matching_age_terms)}")
    else:
        print("  ✗ No age terms found")
        return False
    
    print("All criteria met!")
    return True

def parse_preprint(preprint):
    data = {}
    try:
        attributes = preprint.get('attributes', {})
        
        # Extract basic metadata
        data['id'] = preprint.get('id', '')
        data['title'] = attributes.get('title', '')
        
        # Handle description: Get just the first paragraph for cleaner CSV
        description = attributes.get('description', '')
        if description:
            first_para = description.split('\n\n')[0] if '\n\n' in description else description
            if len(first_para) > 150:
                first_para = first_para[:147] + '...'
            first_para = re.sub(r'\s+', ' ', first_para).strip()
            data['description'] = first_para
        else:
            data['description'] = ''
        
        data['date_created'] = attributes.get('date_created', '')
        data['date_modified'] = attributes.get('date_modified', '')
        data['date_published'] = attributes.get('date_published', '')
        
        data['doi'] = attributes.get('doi', '')
        
        tags = attributes.get('tags', [])
        data['tags'] = ', '.join(tags) if tags else ''
        
        links = preprint.get('links', {})
        data['preprint_link'] = links.get('html', '')
        
        # We could fetch contributors and subjects with additional API calls but I'll use placeholders for now
        data['contributors'] = 'N/A'
        data['subjects'] = 'N/A'
        
        # Add the terms that matched our criteria
        data['matching_terms'] = get_matching_terms(data)
        
    except Exception as e:
        print(f"Error parsing preprint entry: {e}")
        print(f"Problematic preprint data: {preprint.get('id', 'Unknown ID')}")
        return None
        
    return data

def get_matching_terms(paper_data):
    matching_terms = []

    text = (paper_data.get('title', '').lower() + ' ' + 
            paper_data.get('description', '').lower() + ' ' + 
            paper_data.get('tags', '').lower())
    
    for term in POPULATION_TERMS:
        if term in text:
            matching_terms.append(term)
    
    for term in INTERVENTION_TERMS:
        if term in text:
            matching_terms.append(term)
            
    for term in AGE_TERMS:
        if term in text:
            matching_terms.append(term)
            
    return ', '.join(matching_terms)

def is_duplicate(new_entry, existing_entries):
    base_id = new_entry['id'].split('_v')[0] if '_v' in new_entry['id'] else new_entry['id']
    
    for entry in existing_entries:
        existing_base_id = entry['id'].split('_v')[0] if '_v' in entry['id'] else entry['id']
        if base_id == existing_base_id:
            if new_entry['id'] > entry['id']:
                existing_entries.remove(entry)
                return False
            else:
                return True
                
    return False

def save_to_csv(data_list, filename):
    if not data_list:
        print("No data to save.")
        return
    
    headers = list(data_list[0].keys())
        
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            writer.writerows(data_list)
        print(f"Successfully saved {len(data_list)} results to {filename}")
    except IOError as e:
        print(f"Error writing to CSV file {filename}: {e}")


def main():
    all_results = []
    current_page = 1
    total_found = 0
    matched_count = 0
    duplicate_count = 0
    
    print(f"\nSearching PsyArXiv preprints...")
    print(f"Population terms (filtering for): {', '.join(POPULATION_TERMS)}")
    print(f"Intervention terms (filtering for): {', '.join(INTERVENTION_TERMS)}")
    print(f"Age terms (filtering for): {', '.join(AGE_TERMS)}")
    print(f"Note: Using manual filtering since the OSF API doesn't support full-text search")
    print(f"Max pages to search: {MAX_PAGES}")
    print(f"Results per page: {MAX_RESULTS_PER_PAGE}")
    
    while current_page <= MAX_PAGES:
        print(f"\nRequesting page {current_page} of {MAX_PAGES}...")
        json_data = fetch_results(page=current_page)
        
        if not json_data:
            print("Failed to fetch data or no more results. Stopping.")
            break
            
        preprints = json_data.get('data', [])
        if not preprints:
            print("No more preprints found in the response.")
            break
        
        total_found += len(preprints)
        print(f"Found {len(preprints)} preprints in this batch. Filtering based on criteria...")
        
        for preprint in preprints:
            if passes_filter_criteria(preprint):
                parsed_data = parse_preprint(preprint)
                if parsed_data:
                    # Check for duplicates (different versions)
                    if is_duplicate(parsed_data, all_results):
                        duplicate_count += 1
                        print(f"  Skipping duplicate: {parsed_data['id']}")
                    else:
                        all_results.append(parsed_data)
                        matched_count += 1
                        print(f"  Added: {parsed_data['id']}")
        
        print(f"After filtering, kept {matched_count} unique preprints so far.")
        
        # Get pagination links
        links = json_data.get('links', {})
        next_link = links.get('next')
        
        if not next_link:
            print("No more pages available.")
            break
            
        current_page += 1
        
        if current_page <= MAX_PAGES:
            print(f"Waiting {WAIT_TIME} seconds before next request...")
            time.sleep(WAIT_TIME)
            
    if all_results:
        save_to_csv(all_results, OUTPUT_CSV)
        print(f"\nFinished processing.")
        print(f"Total preprints examined: {total_found}")
        print(f"Total matching results: {matched_count}")
        print(f"Duplicates skipped: {duplicate_count}")
        print(f"Results saved to: {OUTPUT_CSV}")
    else:
        print("\nNo results were found matching your search criteria.")

if __name__ == "__main__":
    main()
