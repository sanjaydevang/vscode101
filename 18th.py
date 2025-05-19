import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
import logging
from typing import Optional, List

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SECRiskFactorExtractor:
    def __init__(self, user_agent: str):
        self.headers = {'User-Agent': user_agent}

    def get_filing_url(self, cik: str, year: str) -> Optional[str]:
        cik_padded = str(cik).zfill(10)
        base_url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
        try:
            response = requests.get(base_url, headers=self.headers)
            data = response.json()
            filings = data.get("filings", {}).get("recent", {})
            for i in range(len(filings["form"])):
                if filings["form"][i] == "10-K":
                    file_year = filings["filingDate"][i][:4]
                    report_year = filings.get("reportDate", [])[i][:4] if i < len(filings.get("reportDate", [])) else None
                    if file_year in [year, str(int(year)+1)] or report_year == year:
                        acc_no = filings["accessionNumber"][i].replace("-", "")
                        return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no}/index.json"
        except Exception as e:
            logging.warning(f"Error fetching URL for CIK {cik}: {e}")
        return None

    def get_full_document_url(self, filing_url: str) -> Optional[str]:
        try:
            json_data = requests.get(filing_url, headers=self.headers).json()
            files = json_data['directory']['item']
            html_file = next((f['name'] for f in files if f['name'].endswith('.htm')), None)
            if html_file:
                return filing_url.replace('index.json', html_file)
        except Exception as e:
            logging.warning(f"Error fetching document URL from {filing_url}: {e}")
        return None

    def extract_risk_factor_titles(self, document_url: str) -> List[str]:
        titles = []
        try:
            response = requests.get(document_url, headers=self.headers)
            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text()
            match = re.search(r'ITEM\s+1A[\.\s\-]*RISK\s+FACTORS(.*?)(ITEM\s+1B|ITEM\s+2)', text, re.DOTALL | re.IGNORECASE)
            if match:
                section = match.group(1)
                extracted_titles = re.findall(r'\n([A-Z][A-Z\s,0-9\(\)\-]{10,})\n', section)
                titles.extend([t.strip() for t in extracted_titles if 20 < len(t.strip()) < 200 and t.strip().endswith('.')])

            if not titles:
                for tag in soup.find_all(['b', 'strong']):
                    txt = tag.get_text().strip()
                    if 20 < len(txt) < 200 and txt.endswith('.'):
                        titles.append(txt)

            blacklist = [
                'exhibit', 'item no', 'table of contents', 'cover page', '10-k',
                'pharmacal', 'executive compensation', 'director', 'governance',
                'item 9b', 'item 14', 'item 9.', 'item 9', 'other information',
                'significant management expertise', 'zioptan', 'product acquisition', 'benefit programs',
                'legal proceedings', 'mine safety disclosures', 'note 22'
            ]
            cleaned_titles = []
            for t in titles:
                t_clean = re.sub(r'[\n\r\t"\\]+', ' ', t).strip()
                t_clean = re.sub(r'\s+', ' ', t_clean)
                t_lower = t_clean.lower()
                if (
                    len(t_clean.split()) > 4
                    and all(x not in t_lower for x in blacklist)
                    and not re.match(r'^item\s+\d+[a-z]?\.?', t_lower)
                    and not re.search(r'\b(note|inc|corp|ltd|llc|company|limited)\b', t_lower)
                    and not re.search(r'\b(item\s+\d+[a-z]?|note\s+\d+|legal proceedings|fees and services|mine safety|ownership)\b', t_lower)
                    and not t_lower.startswith("item ")
                    and not t_lower.endswith("inc.")
                ):
                    cleaned_titles.append(t_clean)

            return list(set(cleaned_titles))
        except Exception as e:
            logging.error(f"Error extracting titles from {document_url}: {e}")
            return []

    def extract_filing_date(self, text: str, fallback_year: str) -> str:
        try:
            matches = re.findall(r'filed on (\w+ \d{1,2}, \d{4})', text, re.IGNORECASE)
            if not matches:
                matches = re.findall(r'filing date[:\s]+(\w+ \d{1,2}, \d{4})', text, re.IGNORECASE)
            if not matches:
                matches = re.findall(r'(\w+ \d{1,2}, \d{4})', text[-3000:], re.IGNORECASE)  # last page
            for m in matches:
                try:
                    return pd.to_datetime(m).strftime('%Y-%m-%d')
                except:
                    continue
        except:
            pass
        return ""

    def extract_reporting_date(self, text: str, filing_year: str) -> str:
        match = re.search(r'for the fiscal year ended ([A-Za-z]+ \d{1,2}, \d{4})', text, re.IGNORECASE)
        if match:
            try:
                return pd.to_datetime(match.group(1)).strftime('%Y-%m-%d')
            except Exception:
                pass
        return ""

    def process_all_filings(self, input_file: str, output_file: str):
        df = pd.read_csv(input_file)
        df.columns = df.columns.str.strip().str.lower()
        results = []

        for idx, row in df.iterrows():
            cik = str(int(float(row['cik']))).zfill(10)
            year = str(int(float(row['filingyear']))).strip()
            logging.info(f"Processing CIK {cik} for year {year}")

            filing_url = self.get_filing_url(cik, year)
            if not filing_url:
                logging.warning(f"No filing found for {cik} in {year}")
                continue

            doc_url = self.get_full_document_url(filing_url)
            if not doc_url:
                logging.warning(f"No document URL found for CIK {cik}")
                continue

            response = requests.get(doc_url, headers=self.headers)
            soup = BeautifulSoup(response.text, "html.parser")
            full_text = soup.get_text()

            filing_date = self.extract_filing_date(full_text, year)
            reporting_date = self.extract_reporting_date(full_text, year)

            titles = self.extract_risk_factor_titles(doc_url)
            logging.info(f"Found {len(titles)} risk titles for CIK {cik} ({year})")

            for title in titles:
                results.append({
                    'CIK': cik,
                    'Filing Year': year,
                    'Filing Date': filing_date,
                    'Reporting Date': reporting_date,
                    'RFDTitle': title
                })

            time.sleep(1)

        result_df = pd.DataFrame(results)
        result_df.to_csv(output_file, index=False)
        logging.info(f"Saved results to {output_file}")

if __name__ == "__main__":
    extractor = SECRiskFactorExtractor(user_agent='RA-Sanjay/1.0 (sanjay.devang@gwu.edu)')
    extractor.process_all_filings('rasamplemini_rfdtitle.csv', 'rasamplemini_rfdtitle_completed.csv')
