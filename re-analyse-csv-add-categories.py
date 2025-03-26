import pandas as pd
import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime

# Load OpenAI API key
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_KEY"))

INPUT_PATH = "semantic_scholar_filtered.csv"
OUTPUT_PATH = "semantic_scholar_reanalyzed.csv"
FLAGGED_PATH = "semantic_scholar_needs_full_text.csv"
ERROR_LOG = "errors.log"

# JSON schema for classification
json_schema = {
    "type": "object",
    "properties": {
        "digital_intervention": {"type": "string", "enum": ["Yes", "No"]},
        "targets_adhd": {"type": "string", "enum": ["Yes", "No"]},
        "targets_autism": {"type": "string", "enum": ["Yes", "No"]},
        "targets_adults": {"type": "string", "enum": ["Yes", "No"]},
        "study_category": {"type": "string"},
        "rationale": {"type": "string"}
    },
    "required": ["digital_intervention", "targets_adhd", "targets_autism", "targets_adults", "study_category", "rationale"]
}

# Parse JSON output from prior LLM run (if available)
def parse_llm_result(llm_output):
    try:
        parsed = json.loads(llm_output)
        return {
            "Digital Intervention": parsed.get("digital_intervention", "Unknown"),
            "Targets ADHD": parsed.get("targets_adhd", "Unknown"),
            "Targets Autism": parsed.get("targets_autism", "Unknown"),
            "Targets Adults": parsed.get("targets_adults", "Unknown"),
            "Study Category": parsed.get("study_category", "Unknown"),
            "LLM Rationale": parsed.get("rationale", "")
        }
    except Exception:
        return {
            "Digital Intervention": "Unknown",
            "Targets ADHD": "Unknown",
            "Targets Autism": "Unknown",
            "Targets Adults": "Unknown",
            "Study Category": "Unknown",
            "LLM Rationale": "Failed to parse"
        }

# GPT classification
def classify_study(title, abstract):
    system_prompt = (
        "You are a research assistant analyzing academic papers. "
        "Classify each study based on its focus. "
        "Check if it describes a digital intervention and if it targets ADHD, Autism, or both. "
        "Also check if it targets adults. "
        "Assign it to one of the following categories:\n"
        "1. Digital Cognitive Training\n"
        "2. Mobile Apps for ADHD/Autism\n"
        "3. Telehealth & Online Therapy\n"
        "4. Gamification & Serious Games\n"
        "5. Wearables & Assistive Tech\n"
        "6. Digital Behavioral Therapy\n"
        "7. Social Skills Training & Communication\n"
        "8. AI & Machine Learning in ADHD/Autism\n"
        "9. Mixed Neurodivergent Populations\n"
        "10. Non-Relevant Digital Research\n"
        "Respond using this JSON schema: "
        "'digital_intervention', 'targets_adhd', 'targets_autism', 'targets_adults', 'study_category', 'rationale'"
    )

    user_prompt = f"Title: {title}\nAbstract: {abstract}"

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "StudyClassification",
                "schema": json_schema
            }
        }
    )
    return json.loads(response.choices[0].message.content)

# Logic for flagging full-text review
def needs_full_text_review(row):
    d = row["Digital Intervention"].strip().lower()
    a = row["Targets ADHD"].strip().lower()
    u = row["Targets Autism"].strip().lower()
    adults = row["Targets Adults"].strip().lower()
    cat = row["Study Category"].strip()

    if d == "yes" and a == "yes" and u == "yes" and adults == "yes":
        return "No - definitely a match"
    if d == "no" or (a == "no" and u == "no"):
        return "No - definitely not a match"
    if d == "no" and cat in ["Digital Cognitive Training", "Telehealth & Online Therapy", "Mobile Apps for ADHD/Autism"]:
        return "Yes"
    if (a == "yes" and u == "no") or (u == "yes" and a == "no"):
        return "Yes"
    if adults == "no" and cat in ["Gamification & Serious Games", "Digital Behavioral Therapy", "Telehealth & Online Therapy"]:
        return "Yes"
    if cat in ["AI & Machine Learning in ADHD/Autism", "Mixed Neurodivergent Populations"]:
        return "Yes"
    return "No - definitely not a match"

# Log errors to file
def log_error(title, error_msg):
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] {title}\n{error_msg}\n\n")

# Main logic
def main():
    if os.path.exists(OUTPUT_PATH):
        df = pd.read_csv(OUTPUT_PATH)
        print("🔄 Resuming from previous run...")
    else:
        df = pd.read_csv(INPUT_PATH)
        # If "LLM Filter Result" exists, parse and add columns
        if "LLM Filter Result" in df.columns:
            parsed = df["LLM Filter Result"].apply(parse_llm_result)
            df = pd.concat([df, pd.DataFrame(parsed.tolist())], axis=1)

    # Add output columns if missing
    for col in ["Digital Intervention", "Targets ADHD", "Targets Autism", "Targets Adults", "Study Category", "LLM Rationale"]:
        if col not in df.columns:
            df[col] = None

    for idx, row in df.iterrows():
        if pd.notna(row["Digital Intervention"]):
            continue

        title, abstract = row["Title"], row["Abstract"]
        print(f"\n📄 Processing: {title}")
        try:
            result = classify_study(title, abstract)
            df.at[idx, "Digital Intervention"] = result["digital_intervention"]
            df.at[idx, "Targets ADHD"] = result["targets_adhd"]
            df.at[idx, "Targets Autism"] = result["targets_autism"]
            df.at[idx, "Targets Adults"] = result["targets_adults"]
            df.at[idx, "Study Category"] = result["study_category"]
            df.at[idx, "LLM Rationale"] = result["rationale"]
            df.to_csv(OUTPUT_PATH, index=False)
        except Exception as e:
            log_error(title, str(e))
            print(f"❌ Error: {e}")

    # After all classification, compute full-text review flag
    df["Needs Full-Text Review"] = df.apply(needs_full_text_review, axis=1)
    df.to_csv(FLAGGED_PATH, index=False)
    print(f"\n✅ Saved classified output to: {OUTPUT_PATH}")
    print(f"🔍 Saved full-text review flags to: {FLAGGED_PATH}")

if __name__ == "__main__":
    main()
