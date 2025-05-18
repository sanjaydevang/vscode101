import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time

# Helper function to get the 10-K filing URL
def get_filing_url(cik, filing_year):
    base_url = f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json"
    headers = {'User-Agent': 'ResearchAssistant/1.0 (s.devang@gwmail.gwu.edu)'}
    try:
        response = requests.get(base_url, headers=headers)
        data = response.json()
    except:
        return None, None

    filings = data.get("filings", {}).get("recent", {})
    for i in range(len(filings["form"])):
        if filings["form"][i] == "10-K" and str(filing_year) in filings["filingDate"][i]:
            accession_num = filings["accessionNumber"][i].replace("-", "")
            filing_date = filings["filingDate"][i]
            url = f"https://www.sec.gov/Archives/edgar/data/{str(cik)}/{accession_num}/index.json"
            return url, filing_date
    return None, None

# Helper function to extract risk titles from Item 1A
def extract_risk_titles(filing_doc_url):
    headers = {'User-Agent': 'ResearchAssistant/1.0 (your_email@example.com)'}
    response = requests.get(filing_doc_url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    text = soup.get_text()

    # Extract text between Item 1A and Item 1B
    match = re.search(r'ITEM\s+1A[^\n]*?\n(.*?)(ITEM\s+1B|\nITEM\s+1B)', text, re.DOTALL | re.IGNORECASE)
    if not match:
        return []

    item_1a_text = match.group(1)

    # Extract lines that resemble risk titles
    possible_titles = re.findall(r'\n\s*([A-Z][A-Z \-,\(\)\']{10,100})\n', item_1a_text)
    unique_titles = list(set([title.strip() for title in possible_titles if len(title.strip()) > 10]))
    return unique_titles

# Load and normalize the CSV
df = pd.read_csv('rasamplemini_rfdtitle.csv')
df.columns = df.columns.str.strip().str.lower()

results = []

for idx, row in df.iterrows():
    cik = str(row['cik']).strip()
    filing_year = str(row['filingyear']).strip()

    print(f"\n🔍 Processing CIK {cik} - Year {filing_year}")

    filing_index_url, filing_date = get_filing_url(cik, filing_year)
    if not filing_index_url:
        print("❌ Filing not found")
        continue

    print("✅ Found filing index URL:", filing_index_url)

    index_json = requests.get(filing_index_url).json()
    files = index_json['directory']['item']
    html_file = next((f['name'] for f in files if f['name'].endswith('.htm')), None)

    if not html_file:
        print("❌ No .htm document found.")
        continue

    full_doc_url = filing_index_url.replace('index.json', html_file)
    print("📄 Extracting from:", full_doc_url)

    try:
        titles = extract_risk_titles(full_doc_url)
        if not titles:
            print("⚠️ No risk titles found.")
        for title in titles:
            results.append({
                'CIK': cik,
                'Filing Year': filing_year,
                'Filing Date': filing_date,
                'Reporting Date': '',  # Can be filled manually or from further parsing
                'RFDTitle': title
            })
    except Exception as e:
        print("⚠️ Error extracting risk titles:", e)

    time.sleep(1)  # Respect SEC rate limits

# Export result
output_df = pd.DataFrame(results)
output_df.to_csv('rasamplemini_rfdtitle_completed.csv', index=False)
print("\n✅ Extraction complete. Results saved to rasamplemini_rfdtitle_completed.csv")
