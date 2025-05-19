class Solution:
    def isAnagram(self, s: str, t: str) -> bool:
        s = s.replace(" ","").lower()
        t = t.replace(" ","").lower()
        
        if len(s) != len(t):
            return False
        
        count = {}
        
        for val1 in s:
            if val1 in count:
                count[val1] +=1
            else:
                count[val1] =1
        
        for val2 in t:
            if val2 in count:
                count[val2] -=1
            else:
                count[val2] =1
        
        for k in count:
            if count[k] != 0:
                return False
            
        return True 
    
if __name__ == "__main__":
    s = Solution()
    
    print(s.isAnagram("listen", "silent"))        # True
    print(s.isAnagram("triangle", "integral"))    # True
    print(s.isAnagram("hello", "world"))          # False
    print(s.isAnagram("Debit Card", "Bad Credit"))# True



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
    # Try to find the reporting date (fiscal year end)
    patterns = [
        r"For the fiscal year ended\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"Fiscal Year Ended\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"for the year ended\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})"
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                return datetime.strptime(m.group(1).replace(',', ''), "%B %d %Y").strftime("%-m/%-d/%Y")
            except:
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
    titles = []

    # 1. Try bold/strong/italic/underline as before
    for tag in soup.find_all(['b', 'strong', 'i', 'em', 'u']):
        t = tag.get_text().strip()
        if 20 <= len(t) <= 200:
            titles.append(t)

    # 2. Try all-caps lines as before
    plain = soup.get_text('\n')
    for line in plain.split('\n'):
        if line.isupper() and 20 <= len(line) <= 200:
            titles.append(line.strip())

    # 3. Heuristic: first sentence of each paragraph
    paragraphs = [p.get_text() for p in soup.find_all('p')]
    if not paragraphs:  # fallback: split by double newline
        paragraphs = plain.split('\n\n')
    for para in paragraphs:
        para = para.strip()
        if len(para) < 40:
            continue
        # Take first sentence (up to first period)
        first_sentence = para.split('. ')[0].strip()
        if 20 <= len(first_sentence) <= 200 and first_sentence not in titles:
            titles.append(first_sentence)

    # Remove duplicates, preserve order
    seen = set()
    result = []
    for t in titles:
        t = re.sub(r'\s+', ' ', t)
        if t and t not in seen:
            seen.add(t)
            result.append(t)
    return result

def main():
    df = pd.read_csv("rasamplemini_rfdtitle.csv")
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
