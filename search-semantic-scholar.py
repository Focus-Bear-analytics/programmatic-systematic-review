import requests
import pandas as pd
import os
import time
from dotenv import load_dotenv
from openai import OpenAI

# Load API key
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_KEY"))

# --- Configurable Settings ---
MAX_RESULTS = 500  # Total number of papers to fetch
BATCH_SIZE = 100  # API batch size per request
START_YEAR = 2015  # Only fetch papers published from this year onward
QUERY_VARIANTS = [
    "digital autism ADHD adults",
    "mobile app autism ADHD",
    "software ADHD autism intervention",
    "e-health ADHD autism adults"
]  # Multiple search queries

# --- Search Semantic Scholar with Pagination ---
def search_semantic_scholar(query):
    """
    Fetches academic papers from Semantic Scholar with pagination.
    """
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    headers = {"Accept": "application/json"}
    all_results = []
    offset = 0

    while len(all_results) < MAX_RESULTS:
        params = {
            "query": query,
            "limit": BATCH_SIZE,
            "offset": offset,
            "fields": "title,abstract,authors,year,url,externalIds"
        }

        for attempt in range(5):
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                break
            elif response.status_code == 429:
                wait = 2 ** attempt
                print(f"⚠️ Rate limited. Waiting {wait} seconds before retry...")
                time.sleep(wait)
            else:
                print(f"❌ Error {response.status_code}: {response.text}")
                print("🔍 Query debug info:")
                print(f"   Query: {query}")
                print(f"   Offset: {offset}")
                print(f"   Limit: {BATCH_SIZE}")
                print(f"   Params: {params}")
                break

        else:
            print("❌ Max retries hit. Skipping this batch.")
            break


        data = response.json()
        papers = data.get("data", [])
        
        if not papers:
            break  # Stop if no more results

        all_results.extend(papers)
        offset += BATCH_SIZE  # Move to next batch

        print(f"📄 Retrieved {len(all_results)} papers so far for query: {query}")

        time.sleep(2)  # Respect API rate limits

    return all_results[:MAX_RESULTS]

# --- Filter Studies Matching Digital & AuDHD Criteria ---
def filter_studies(papers):
    keywords_digital = ["digital", "app", "technology", "intervention", "e-health", "mobile", "smartphone", "software"]
    keywords_adhd_autism = ["ADHD", "autism", "AuDHD", "autistic", "attention deficit", "hyperactivity disorder"]

    filtered = []
    for paper in papers:
        # Extract DOI if available
        doi = paper.get("externalIds", {}).get("DOI", "")
        title = paper.get("title", "No Title")
        year = paper.get("year", 0)
        abstract = paper.get("abstract", "")
        url = paper.get("url", "")
        authors = ", ".join([a["name"] for a in paper.get("authors", [])])

        # Ignore papers before START_YEAR
        if year and year < START_YEAR:
            continue

        # Check if title/abstract contain relevant keywords
        text = f"{title} {abstract}".lower()
        if any(k.lower() in text for k in keywords_digital) and any(k.lower() in text for k in keywords_adhd_autism):
            filtered.append({
                "DOI": doi if doi else title,  # Use DOI as key, fallback to title if no DOI
                "Title": title,
                "Abstract": abstract,
                "Authors": authors,
                "Year": year,
                "URL": url
            })
    return filtered

# --- Load Cached Results (Avoid Reprocessing Papers) ---
def load_existing_results(filename="semantic_scholar_filtered.csv"):
    if os.path.exists(filename):
        return pd.read_csv(filename).to_dict(orient="records")
    return []

# --- LLM Filtering with GPT-4o ---
def llm_filter(title, abstract):
    system_prompt = (
        "You are a research assistant helping conduct a systematic literature review. "
        "Only include papers that describe a digital intervention (such as an app or software) "
        "for adults with both ADHD and autism (AuDHD). Be strict."
    )

    user_prompt = f"Title: {title}\nAbstract: {abstract}\n\nPlease respond with:\nInclude: true/false\nRationale: [short explanation]"

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        temperature=0.3,
    )

    return response.choices[0].message.content

# --- Main Workflow ---
def main():
    print("🔍 Searching Semantic Scholar...")

    # Load previous results (cache)
    existing_results = load_existing_results()
    existing_dois = {paper.get("DOI", paper.get("Title")) for paper in existing_results}

    new_papers = []

    for query in QUERY_VARIANTS:
        print(f"\n🔎 Running query: {query}")
        results = search_semantic_scholar(query)
        filtered = filter_studies(results)

        # Skip papers already in cache (by DOI or title)
        fresh_papers = [p for p in filtered if p["DOI"] not in existing_dois]
        print(f"🆕 {len(fresh_papers)} new papers found for query: {query}")

        new_papers.extend(fresh_papers)

    # Apply LLM filtering **only on new papers**
    for paper in new_papers:
        print(f"\n📄 Evaluating: {paper['Title']}")
        result = llm_filter(paper["Title"], paper["Abstract"])
        print(result)
        paper["LLM Filter Result"] = result

    # Combine old + new results and save
    final_results = existing_results + new_papers
    df = pd.DataFrame(final_results)
    df.to_csv("semantic_scholar_filtered.csv", index=False)
    print(f"✅ Saved {len(final_results)} total papers to semantic_scholar_filtered.csv")

if __name__ == "__main__":
    main()
