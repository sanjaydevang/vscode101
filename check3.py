import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
import os

# Set your SEC-registered email address here
HEADERS = {
    'User-Agent': 'your.email@example.com',  # REPLACE WITH YOUR EMAIL
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'www.sec.gov'
}

# Create directory to store debug information
os.makedirs('debug', exist_ok=True)

def get_10k_url(cik, filing_year):
    """Retrieve the 10-K filing URL for a specific company (CIK) and year."""
    cik_str = str(cik).zfill(10)
    filing_year = int(filing_year)
    start_date = f"{filing_year-1}1201"
    end_date = f"{filing_year}1231"

    search_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik_str}&type=10-K&dateb={end_date}&datea={start_date}&owner=exclude&count=40"
    print(f"Searching: {search_url}")

    try:
        time.sleep(0.1)
        response = requests.get(search_url, headers=HEADERS)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table', class_='tableFile2')
        if not table:
            print(f"No filings found for CIK {cik}, Year {filing_year}")
            return None, None

        for row in table.find_all('tr')[1:]:
            cells = row.find_all('td')
            if len(cells) >= 4:
                filing_type = cells[0].text.strip()
                filing_date = cells[3].text.strip()
                if filing_type == "10-K" and str(filing_year) in filing_date:
                    filing_link = cells[1].find('a', href=True)
                    if filing_link:
                        detail_url = f"https://www.sec.gov{filing_link['href']}"
                        print(f"Found filing page: {detail_url}")

                        time.sleep(0.1)
                        detail_response = requests.get(detail_url, headers=HEADERS)
                        detail_soup = BeautifulSoup(detail_response.content, 'html.parser')

                        for table_tag in detail_soup.find_all('table'):
                            for row_tag in table_tag.find_all('tr'):
                                for link_tag in row_tag.find_all('a', href=True):
                                    href = link_tag['href']
                                    if href.endswith('.htm') and not re.search(r'ex-?\d+', href, re.IGNORECASE):
                                        filing_url = f"https://www.sec.gov{href}"
                                        print(f"10-K Document URL: {filing_url}")
                                        return filing_url, pd.to_datetime(filing_date).strftime('%m/%d/%Y')

        print(f"No 10-K document URL found for CIK {cik}, Year {filing_year}")
        return None, None
    except Exception as e:
        print(f"Exception fetching filing URL: {e}")
        return None, None

def extract_reporting_date(text, filing_year):
    """Extract the fiscal year reporting date from the filing text."""
    patterns = [
        r'fiscal year ended ([A-Za-z]+ \d{1,2}, \d{4})',
        r'for the fiscal year ended ([A-Za-z]+ \d{1,2}, \d{4})'
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return pd.to_datetime(match.group(1)).strftime('%m/%d/%Y')
            except:
                pass
    return f'12/31/{int(filing_year)-1}'

def extract_risk_section(html):
    """Extract the risk factor section between Item 1A and Item 1B or Item 2."""
    start_patterns = [r'Item\s*1A\.?\s*Risk\s*Factors']
    end_patterns = [r'Item\s*1B', r'Item\s*2']

    start = None
    for pattern in start_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            start = match.end()
            break
    if start is None:
        return ""

    end = None
    for pattern in end_patterns:
        match = re.search(pattern, html[start:], re.IGNORECASE)
        if match:
            end = start + match.start()
            break
    return html[start:end] if end else html[start:start+100000]

def identify_titles(section):
    """Extract candidate risk factor titles from the risk section."""
    candidates = re.findall(r'(?:\n|\•|\*|\-)+\s*(.*?\.)', section)
    titles = [c.strip() for c in candidates if 20 < len(c.strip()) < 300]
    return list(set(titles))

def main():
    """Main script to orchestrate extraction of risk factors for each CIK and year."""
    df = pd.read_csv("rasamplemini_rfdtitle_input.csv", dtype={'cik': str})
    df.columns = df.columns.str.lower()
    output = []

    for _, row in df.iterrows():
        cik, year = row['cik'], int(row['filingyear'])
        print(f"\nProcessing CIK {cik}, Year {year}")
        url, filing_date = get_10k_url(cik, year)
        if not url:
            output.append({**row, 'filingdate': '', 'reportingdate': '', 'rfdtitle': ''})
            continue

        time.sleep(0.1)
        response = requests.get(url, headers=HEADERS)
        soup = BeautifulSoup(response.content, 'html.parser')
        text = soup.get_text(" ", strip=True)
        html = str(soup)

        reporting_date = extract_reporting_date(text, year)
        risk_text = extract_risk_section(html)
        titles = identify_titles(risk_text)

        if titles:
            for title in titles:
                output.append({
                    'cik': cik,
                    'filingyear': year,
                    'filingdate': filing_date,
                    'reportingdate': reporting_date,
                    'rfdtitle': title
                })
        else:
            output.append({
                'cik': cik,
                'filingyear': year,
                'filingdate': filing_date,
                'reportingdate': reporting_date,
                'rfdtitle': 'NO RISK FACTORS FOUND'
            })
        time.sleep(1)

    pd.DataFrame(output).to_csv("rasamplemini_rfdtitle_output.csv", index=False)
    print("\nCompleted risk factor extraction. Output saved.")

if __name__ == '__main__':
    main()
