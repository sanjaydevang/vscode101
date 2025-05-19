import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
import logging

HEADERS = {
    'User-Agent': 's.devang@gwmail.gwu.edu',
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'www.sec.gov'
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_10k_url_and_filing_date(cik, filing_year):
    cik_padded = str(cik).zfill(10)
    base_url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    try:
        response = requests.get(base_url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        filings = data.get("filings", {}).get("recent", {})
        for i in range(len(filings["form"])):
            if filings["form"][i] == "10-K":
                filing_date = filings["filingDate"][i]
                report_date = filings.get("reportDate", [])[i] if i < len(filings.get("reportDate", [])) else ''
                if filing_date.startswith(str(filing_year)) or report_date.startswith(str(filing_year)):
                    accession = filings["accessionNumber"][i].replace("-", "")
                    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/{accession}-index.htm"
                    return url, filing_date
        logging.warning(f"No 10-K found in year {filing_year} for CIK {cik}")
    except Exception as e:
        logging.error(f"Error fetching JSON for {cik}: {e}")
    return None, None

def extract_reporting_date(text, filing_year):
    match = re.search(r'for the fiscal year ended ([A-Za-z]+ \d{1,2}, \d{4})', text, re.IGNORECASE)
    if match:
        try:
            return pd.to_datetime(match.group(1)).strftime('%Y-%m-%d')
        except Exception:
            pass
    return f'{filing_year}-12-31'

def find_risk_factor_text(soup):
    start_pattern = re.compile(r"item[\s\t]*1a[\s\t]*[\.:]?\s*risk\s*factors", re.IGNORECASE)
    end_pattern = re.compile(r"item[\s\t]*1b[\s\t]*[\.:]?\s*unresolved\s*staff\s*comments", re.IGNORECASE)
    start_tag = None
    end_tag = None

    for el in soup.find_all(string=start_pattern):
        start_tag = el.parent.parent.parent
    for el in soup.find_all(string=end_pattern):
        end_tag = el.parent.parent.parent

    content_tags = []
    risks = []

    if start_tag and end_tag:
        current = start_tag.find_next_sibling()
        while current and current != end_tag:
            content_tags.append(current)
            current = current.find_next_sibling()

        for tag in content_tags:
            if tag.find(['b', 'strong', 'i', 'em', 'u']):
                risks.append(tag.get_text())
    else:
        logging.warning("Start or end tag not found for risk factors section.")
    return risks

def main():
    input_csv_path = "rasamplemini_rfdtitle_9.csv"
    output_csv_path = "rasamplemini_rfdtitle_completed_9out.csv"
    output_rows = []
    df = pd.read_csv(input_csv_path, dtype={'cik': str})
    df.columns = df.columns.str.lower()
    for index, row in df.iterrows():
        cik = row['cik'].zfill(10)
        filing_year = int(row['filingyear'])
        tenk_url, filing_date = get_10k_url_and_filing_date(cik, filing_year)
        if not tenk_url:
            logging.warning(f"Skipping CIK: {cik}, Year: {filing_year} - URL not found")
            continue
        time.sleep(0.1)
        response = requests.get(tenk_url, headers=HEADERS)
        logging.info(f"Fetched 10-K URL: {tenk_url}")
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'lxml')
        text = soup.get_text()
        reporting_date = extract_reporting_date(text, filing_year)
        risk_factor_titles = find_risk_factor_text(soup)

        for title in risk_factor_titles:
            cleaned = re.sub(r'[\n\r\t"\\]+', ' ', title).strip()
            output_rows.append({
                'cik': row['cik'],
                'filingyear': filing_year,
                'filingdate': filing_date,
                'reportingdate': reporting_date,
                'rfdtitle': cleaned
            })
        time.sleep(1)
    output_df = pd.DataFrame(output_rows)
    output_df.to_csv(output_csv_path, index=False)
    logging.info(f"Extraction completed. Output saved to {output_csv_path}")

if __name__ == '__main__':
    main()
