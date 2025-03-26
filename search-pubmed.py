import requests
import xmltodict
import pandas as pd
import time

# --- PubMed Search Function ---
def search_pubmed(query, max_results=100):
    """
    Searches PubMed for papers matching the query and returns metadata.
    """
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": max_results
    }

    response = requests.get(base_url, params=params)
    data = response.json()
    
    pmid_list = data["esearchresult"]["idlist"]
    
    return pmid_list

# --- Fetch Study Details from PubMed ---
def fetch_study_details(pmid_list):
    """
    Retrieves study details (title, abstract, journal, authors) from PubMed.
    """
    if not pmid_list:
        return []

    ids = ",".join(pmid_list)
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {
        "db": "pubmed",
        "id": ids,
        "retmode": "xml"
    }

    response = requests.get(base_url, params=params)
    data = xmltodict.parse(response.content)

    studies = []
    articles = data["PubmedArticleSet"].get("PubmedArticle", [])

    for article in articles:
        medline_citation = article["MedlineCitation"]
        article_data = medline_citation.get("Article", {})

        # Extract Title, Abstract, Journal
        title = article_data.get("ArticleTitle", "No Title Available")
        abstract_data = article_data.get("Abstract", {}).get("AbstractText", "")
        abstract = " ".join(abstract_data) if isinstance(abstract_data, list) else abstract_data
        journal = article_data.get("Journal", {}).get("Title", "Unknown Journal")

        # Extract Authors
        authors_data = article_data.get("AuthorList", {}).get("Author", [])
        authors = ", ".join(
            [
                f"{a.get('ForeName', '')} {a.get('LastName', '')}"
                for a in authors_data
                if isinstance(a, dict) and "ForeName" in a and "LastName" in a
            ]
        )

        studies.append({
            "PMID": medline_citation.get("PMID", {}).get("#text", ""),
            "Title": title,
            "Abstract": abstract,
            "Journal": journal,
            "Authors": authors
        })

    return studies

# --- Filter Studies Matching Digital Intervention & AuDHD Criteria ---
def filter_studies(studies):
    """
    Filters studies that contain terms related to digital interventions and ADHD + Autism.
    """
    keywords_digital = ["digital", "app", "technology", "intervention", "e-health", "mobile", "smartphone", "software"]
    keywords_adhd_autism = ["ADHD", "autism", "AuDHD", "autistic", "attention deficit", "hyperactivity disorder"]

    filtered_studies = []
    for study in studies:
        text = f"{study['Title']} {study['Abstract']}".lower()

        if any(k.lower() in text for k in keywords_digital) and any(k.lower() in text for k in keywords_adhd_autism):
            filtered_studies.append(study)

    return filtered_studies

# --- Run Search & Save to CSV ---
def main():
    # Define search query
    search_query = '("digital" OR "app") AND ("AuDHD" OR ("autism" AND "ADHD")) AND "adults"'
    
    # Search PubMed
    print("🔍 Searching PubMed...")
    pmid_list = search_pubmed(search_query, max_results=100)
    
    # Fetch study details
    print(f"📄 Fetching details for {len(pmid_list)} studies...")
    studies = fetch_study_details(pmid_list)
    
    # Apply filtering
    print("🧹 Filtering relevant studies...")
    filtered_studies = filter_studies(studies)

    # Convert to DataFrame
    df = pd.DataFrame(filtered_studies)
    
    # Save results to CSV
    output_file = "filtered_studies.csv"
    df.to_csv(output_file, index=False)
    print(f"✅ Results saved to {output_file}")

# Execute
if __name__ == "__main__":
    main()
