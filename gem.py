import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime

# Add SEC required headers
HEADERS = {
    'User-Agent': 's.devang@gwmail.gwu.edu',  # Replace with your email
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'www.sec.gov'
}

def get_10k_url(cik, filing_year):
    """
    Constructs the URL for the 10-K filing.
    This function attempts to find the 10-K URL from the SEC EDGAR website.
    It's crucial to adapt this to handle variations in EDGAR's URL structure.
    """
    # Format CIK with leading zeros
    cik = str(cik).zfill(10)
    
    # Set date range for the filing year
    start_date = f"{filing_year}0101"
    end_date = f"{filing_year}1231"
    
    # Construct search URL with date range
    base_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K&dateb={end_date}&datea={start_date}&owner=exclude&count=10"
    
    try:
        # Add delay between requests to comply with SEC guidelines
        time.sleep(0.1)  # 100ms delay
        
        response = requests.get(base_url, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'lxml')
        
        # Find the filing table
        filing_table = soup.find('table', class_='tableFile2')
        if not filing_table:
            print(f"No filing table found for CIK: {cik}, Year: {filing_year}")
            return None
            
        # Look for 10-K filings in the table
        for row in filing_table.find_all('tr')[1:]:  # Skip header row
            cells = row.find_all('td')
            if len(cells) >= 5:
                filing_type = cells[0].text.strip()
                filing_date = cells[3].text.strip()
                
                # Check if this is a 10-K filing from the correct year
                if filing_type == "10-K" and filing_date.startswith(str(filing_year)):
                    # Get the link to the filing detail page
                    filing_link = cells[1].find('a', href=True)
                    if filing_link:
                        detail_url = "https://www.sec.gov" + filing_link['href']
                        
                        # Get the filing detail page
                        time.sleep(0.1)  # Add delay
                        detail_response = requests.get(detail_url, headers=HEADERS)
                        if detail_response.status_code == 200:
                            detail_soup = BeautifulSoup(detail_response.content, 'lxml')
                            
                            # Find the link to the full text filing
                            for table_tag in detail_soup.find_all('table'):
                                for row_tag in table_tag.find_all('tr'):
                                    if 'Complete submission text file' in row_tag.text:
                                        for link_tag in row_tag.find_all('a', href=True):
                                            filing_url = "https://www.sec.gov" + link_tag['href']
                                            return filing_url
        
        print(f"10-K URL not found for CIK: {cik}, Year: {filing_year}")
        return None

    except requests.exceptions.RequestException as e:
        print(f"Error fetching EDGAR page for CIK {cik}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error for CIK {cik}: {e}")
        return None

def extract_risk_factor_titles_from_text(text):
    # Patterns for Item 1A section
    start_patterns = [
        r"Item\\s+1A\\.?\\s*Risk\\s+Factors",
        r"ITEM\\s+1A\\.?\\s*RISK\\s+FACTORS"
    ]
    end_patterns = [
        r"Item\\s+1B\\.?\\s*Unresolved\\s+Staff\\s+Comments",
        r"ITEM\\s+1B\\.?\\s*UNRESOLVED\\s+STAFF\\s+COMMENTS",
        r"Item\\s+2\\.?\\s*Properties",
        r"ITEM\\s+2\\.?\\s*PROPERTIES"
    ]

    # Find start of Item 1A
    start_match = None
    for pattern in start_patterns:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        if matches:
            start_match = matches[0]
            break
    if not start_match:
        return []

    # Find end of Item 1A
    end_match = None
    for pattern in end_patterns:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        if matches:
            for match in matches:
                if match.start() > start_match.end():
                    end_match = match
                    break
            if end_match:
                break

    # Extract section text
    if start_match and end_match:
        section_text = text[start_match.end():end_match.start()]
    elif start_match:
        section_text = text[start_match.end():start_match.end() + 20000]  # Fallback chunk
    else:
        return []

    # Split section into paragraphs
    paragraphs = re.split(r'\\n{2,}', section_text)

    # Filter for likely risk factor titles
    titles = []
    for para in paragraphs:
        para = para.strip()
        if (para and para[0].isupper() and para.endswith('.') and
            30 <= len(para) <= 250 and
            not para.isupper() and
            not para.lower().startswith('item 1a') and
            not para.lower().startswith('unresolved staff comments') and
            not para.lower().startswith('legal proceedings')):
            titles.append(para)

    # Remove duplicates while preserving order
    seen = set()
    unique_titles = []
    for t in titles:
        if t not in seen:
            unique_titles.append(t)
            seen.add(t)

    return unique_titles

def extract_filing_and_reporting_dates(text, filing_year):
    # Try to extract reporting date from the text
    reporting_date = None
    match = re.search(r'for the fiscal year ended ([A-Za-z]+ \d{1,2}, \d{4})', text, re.IGNORECASE)
    if match:
        try:
            reporting_date = pd.to_datetime(match.group(1)).strftime('%Y-%m-%d')
        except Exception:
            reporting_date = None
    if not reporting_date:
        reporting_date = f'{filing_year}-12-31'
    return reporting_date

def main():
    input_csv_path = "rasamplemini_rfdtitle.csv"
    output_csv_path = "rasamplemini_rfdtitle_output.csv"
    output_rows = []

    df = pd.read_csv(input_csv_path, dtype={'cik': str})
    df.columns = df.columns.str.lower()

    for index, row in df.iterrows():
        cik = row['cik'].zfill(10)
        filing_year = int(row['filingyear'])

        tenk_url = get_10k_url(cik, filing_year)
        if not tenk_url:
            print(f"Skipping CIK: {cik}, Year: {filing_year} - URL not found")
            continue

        time.sleep(0.1)
        response = requests.get(tenk_url, headers=HEADERS)
        response.raise_for_status()
        text = response.text

        # Extract dates
        reporting_date = extract_filing_and_reporting_dates(text, filing_year)
        filing_date = None  # You can try to extract this from the SEC page if needed

        # Extract risk factor titles
        risk_factor_titles = extract_risk_factor_titles_from_text(text)

        for title in risk_factor_titles:
            output_rows.append({
                'cik': cik,
                'filingyear': filing_year,
                'filingdate': filing_date,
                'reportingdate': reporting_date,
                'rfdtitle': title
            })
        time.sleep(1)

    output_df = pd.DataFrame(output_rows)
    output_df.to_csv(output_csv_path, index=False)
    print(f"Extraction completed. Output saved to {output_csv_path}")

if __name__ == '__main__':
    main()