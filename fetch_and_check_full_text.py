import os
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time

# Configurations
INPUT_CSV = "semantic_scholar_filtered.csv"  # Original filtered dataset
OUTPUT_CSV = "semantic_scholar_full_text_checked.csv"  # Updated dataset with full-text info
TEXT_FOLDER = "full_texts/"  # Folder to store extracted text
HEADERS = {"User-Agent": "Mozilla/5.0"}

# Ensure text storage directory exists
os.makedirs(TEXT_FOLDER, exist_ok=True)

# Function to resolve DOI to publisher URL
def resolve_doi_to_url(doi):
    try:
        url = f"https://doi.org/{doi}"
        response = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=10)
        return response.url
    except Exception:
        return None

# Function to fetch HTML and extract text
def fetch_html_from_url(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200 and "text/html" in response.headers.get("Content-Type", ""):
            return response.text
        return None
    except Exception:
        return None

# Function to clean and extract readable text from HTML
def extract_text_from_html(html, max_chars=10000):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "header", "footer", "nav", "form"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return text[:max_chars]  # Truncate long text

# Function to check if full text contains missing key terms
def check_for_missing_terms(abstract, full_text):
    missing_terms = []
    if "autism" not in abstract.lower() and "autism" in full_text.lower():
        missing_terms.append("autism")
    if "adhd" not in abstract.lower() and "adhd" in full_text.lower():
        missing_terms.append("adhd")
    return ", ".join(missing_terms) if missing_terms else "No"

# Main processing function
def main():
    # Load dataset
    df = pd.read_csv(INPUT_CSV)

    # Ensure required columns exist
    if "Needs Full-Text Review" not in df.columns or "DOI" not in df.columns:
        print("CSV missing required columns: 'DOI' and 'Needs Full-Text Review'")
        return

    # Process only rows where full-text review is required
    df_filtered = df[df["Needs Full-Text Review"].str.strip().str.lower() == "yes"].copy()

    print(f"🔍 Processing {len(df_filtered)} studies requiring full-text review...")

    for idx, row in df_filtered.iterrows():
        doi = row.get("DOI", "").strip()
        abstract = row.get("Abstract", "")

        if not doi:
            df.at[idx, "Full Text File"] = "No DOI"
            df.at[idx, "Resolved in Full Text"] = "No"
            continue

        # Resolve DOI to a full-text URL
        resolved_url = resolve_doi_to_url(doi)
        if not resolved_url:
            df.at[idx, "Full Text File"] = "Could not resolve DOI"
            df.at[idx, "Resolved in Full Text"] = "No"
            continue

        # Fetch full-text HTML
        html = fetch_html_from_url(resolved_url)
        if not html:
            df.at[idx, "Full Text File"] = f"Failed to fetch HTML from {resolved_url}"
            df.at[idx, "Resolved in Full Text"] = "No"
            continue

        # Extract text from HTML
        full_text = extract_text_from_html(html)

        # Save extracted text to file
        filename = f"{TEXT_FOLDER}{doi.replace('/', '_')}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(full_text)

        # Check if missing terms are resolved
        resolved_terms = check_for_missing_terms(abstract, full_text)
        resolved_flag = "Yes" if resolved_terms != "No" else "No"

        # Update dataset
        df.at[idx, "Full Text File"] = filename
        df.at[idx, "Resolved in Full Text"] = resolved_flag

        print(f"✅ Processed {doi} - Resolved Terms: {resolved_terms}")

        # Respect rate limits
        time.sleep(2)

    # Save updated dataset
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"📂 Results saved to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
