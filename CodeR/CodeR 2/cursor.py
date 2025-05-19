import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import time

USER_AGENT = "s.devang@email.gwu.edu"  # Use your email per SEC guidelines
HEADERS = {'User-Agent': USER_AGENT}

def get_10k_filing_url_and_date(cik, filing_year):
    search_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K&dateb={filing_year}1231&owner=exclude&count=100"
    resp = requests.get(search_url, headers=HEADERS)
    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.find("table", class_="tableFile2")
    if not table:
        return None, None
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        filing_type = cells[0].text.strip()
        filing_date = cells[3].text.strip()
        if filing_type == "10-K" and filing_date.startswith(str(filing_year)):
            doc_link = cells[1].find("a")["href"]
            doc_url = "https://www.sec.gov" + doc_link
            # Now get the full text file link
            doc_resp = requests.get(doc_url, headers=HEADERS)
            doc_soup = BeautifulSoup(doc_resp.text, "lxml")
            for row2 in doc_soup.find_all("tr"):
                if "Complete submission text file" in row2.text:
                    file_link = row2.find("a")["href"]
                    filing_url = "https://www.sec.gov" + file_link
                    return filing_url, filing_date
    return None, None

def extract_reporting_date(text):
    # Only search the first 5000 characters for speed and accuracy
    head = text[:5000]
    patterns = [
        r"For the fiscal year ended[:\s]*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"Fiscal Year Ended[:\s]*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"For the year ended[:\s]*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"As of[:\s]*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"Period ended[:\s]*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"Year ended[:\s]*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"Ended[:\s]*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"([A-Za-z]+\s+\d{1,2},\s+\d{4})\s*\\n\s*10-K",  # Sometimes appears before 10-K
    ]
    for pat in patterns:
        m = re.search(pat, head, re.IGNORECASE)
        if m:
            try:
                return datetime.strptime(m.group(1).replace(',', ''), "%B %d %Y").strftime("%-m/%-d/%Y")
            except Exception as e:
                continue
    return ""

def extract_item_1a_section(text):
    # More robust regex for Item 1A start
    start = re.search(r'item\s*1a[\.\:\-]?\s*(risk factors)?', text, re.IGNORECASE)
    if not start:
        return None
    start_idx = start.start()
    # More robust regex for Item 1B or next item
    end = re.search(r'item\s*1b[\.\:\-]?\s*(unresolved staff comments)?|item\s*2[\.\:\-]?\s*(properties)?', text[start_idx:], re.IGNORECASE)
    end_idx = start_idx + end.start() if end else start_idx + 20000  # fallback: 20k chars
    return text[start_idx:end_idx]

def extract_risk_titles(section):
    soup = BeautifulSoup(section, "lxml")
    plain = soup.get_text('\n')
    lines = [line.strip() for line in plain.split('\n') if line.strip()]
    titles = []
    skip_intro = True
    for line in lines:
        # Skip the section header and intro
        if skip_intro:
            if line.lower().startswith("the following is a description"):
                continue
            if line.lower().startswith("we are affected by factors"):
                skip_intro = False  # Found first title
        # Heuristic: Standalone, reasonably long, not all-caps, not a bullet
        if 20 <= len(line) <= 200 and not line.isupper() and not line.startswith('•') and not line.endswith(':'):
            titles.append(line)
    return titles

def main():
    df = pd.read_csv("rasamplemini_rfdtitle-new.csv")
    df.columns = [col.strip().lower() for col in df.columns]
    output_rows = []
    for idx, row in df.iterrows():
        cik = str(int(float(row['cik']))).zfill(10)
        filing_year = int(row['filingyear'])
        print(f"Processing CIK {cik}, year {filing_year}...")
        filing_url, filing_date = get_10k_filing_url_and_date(cik, filing_year)
        if not filing_url:
            print(f"Could not find filing for CIK {cik}, year {filing_year}")
            continue
        filing_resp = requests.get(filing_url, headers=HEADERS)
        filing_text = filing_resp.text
        # Extract reporting date
        reporting_date = extract_reporting_date(filing_text)
        # Format filing date as m/d/yyyy
        try:
            filing_date_fmt = datetime.strptime(filing_date, "%Y-%m-%d").strftime("%-m/%-d/%Y")
        except:
            filing_date_fmt = filing_date
        # Extract Item 1A section
        section = extract_item_1a_section(filing_text)
        if not section:
            print(f"Could not extract Item 1A for CIK {cik}, year {filing_year}")
            continue
        else:
            print(f"Extracted Item 1A section for CIK {cik}, year {filing_year} (first 500 chars):\n{section[:500]}")
        # Extract risk factor titles
        titles = extract_risk_titles(section)
        if not titles:
            print(f"No risk titles found for CIK {cik}, year {filing_year}")
            continue
        for title in titles:
            output_rows.append({
                "CIK": cik,
                "Filing Year": filing_year,
                "Filing Date": filing_date_fmt,
                "Reporting Date": reporting_date,
                "RFDTitle": title
            })
        time.sleep(0.5)  # Be nice to SEC servers
    outdf = pd.DataFrame(output_rows)
    outdf.columns = ['cik', 'filingyear', 'filingdate', 'reportingdate', 'RFDTitle']
    outdf.to_csv("rasamplemini_rfdtitle_completed.csv", index=False)
    print("Done! Output written to rasamplemini_rfdtitle_completed.csv")

if __name__ == "__main__":
    main()
