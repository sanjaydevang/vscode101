import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time

# Replace with your email
HEADERS = {
    'User-Agent': 'your.email@example.com',
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'www.sec.gov'
}

def get_10k_url_and_filing_date(cik, filing_year):
    """Get the 10-K URL and filing date"""
    # Make sure CIK is a clean string (no decimal points)
    cik = str(cik).replace('.0', '')
    cik = cik.zfill(10)
    
    # Make sure filing_year is an integer
    if isinstance(filing_year, float):
        filing_year = int(filing_year)
        
    start_date = f"{filing_year}0101"
    end_date = f"{filing_year}1231"
    base_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K&dateb={end_date}&datea={start_date}&owner=exclude&count=10"
    
    print(f"Searching: {base_url}")
    
    try:
        time.sleep(0.1)
        response = requests.get(base_url, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'lxml')
        filing_table = soup.find('table', class_='tableFile2')

        if not filing_table:
            print(f"No filing table found for CIK: {cik}, Year: {filing_year}")
            return None, None

        for row in filing_table.find_all('tr')[1:]:
            cells = row.find_all('td')
            if len(cells) >= 5:
                filing_type = cells[0].text.strip()
                filing_date = cells[3].text.strip()
                if filing_type == "10-K" and filing_date.startswith(str(filing_year)):
                    filing_link = cells[1].find('a', href=True)
                    if filing_link:
                        detail_url = "https://www.sec.gov" + filing_link['href']
                        time.sleep(0.1)
                        detail_response = requests.get(detail_url, headers=HEADERS)
                        if detail_response.status_code == 200:
                            detail_soup = BeautifulSoup(detail_response.content, 'lxml')
                            for table_tag in detail_soup.find_all('table'):
                                for row_tag in table_tag.find_all('tr'):
                                    for link_tag in row_tag.find_all('a', href=True):
                                        href = link_tag['href']
                                        if href.endswith('.htm') and not re.search(r'ex-?\d+|ex\d+\.htm', href, re.IGNORECASE):
                                            filing_url = "https://www.sec.gov" + href
                                            return filing_url, filing_date
        print(f"10-K URL not found for CIK: {cik}, Year: {filing_year}")
        return None, None
    except Exception as e:
        print(f"Error fetching 10-K URL for CIK {cik}: {e}")
        return None, None

def extract_reporting_date(text, filing_year):
    """Extract the reporting date from the 10-K filing text"""
    match = re.search(r'for the fiscal year ended ([A-Za-z]+ \d{1,2}, \d{4})', text, re.IGNORECASE)
    if match:
        try:
            return pd.to_datetime(match.group(1)).strftime('%m/%d/%Y')
        except Exception:
            pass
    return f'12/31/{filing_year-1}'

def find_risk_factor_section(soup):
    """Find the risk factor section"""
    html_str = str(soup)
    text_str = soup.get_text()
    
    # Look for risk factor section
    item_1a_patterns = [
        r'Item\s*1A\.?\s*Risk\s*Factors',
        r'ITEM\s*1A\.?\s*RISK\s*FACTORS',
        r'RISK\s+FACTORS'
    ]
    
    item_1b_patterns = [
        r'Item\s*1B',
        r'ITEM\s*1B',
        r'Item\s*2',
        r'ITEM\s*2',
        r'PART\s*II'
    ]
    
    # Find start position
    start_pos = None
    for pattern in item_1a_patterns:
        match = re.search(pattern, html_str, re.IGNORECASE)
        if match:
            start_pos = match.end()
            break
    
    if start_pos is None:
        return None
    
    # Find end position
    end_pos = None
    for pattern in item_1b_patterns:
        match = re.search(pattern, html_str[start_pos:], re.IGNORECASE)
        if match:
            end_pos = start_pos + match.start()
            break
    
    if end_pos is None:
        # Use a reasonable chunk if no end marker found
        end_pos = start_pos + 50000
    
    section_html = html_str[start_pos:end_pos]
    return BeautifulSoup(section_html, 'lxml')

def extract_risk_factor_titles(section_soup):
    """Extract risk factor titles from the section"""
    if section_soup is None:
        return []
    
    titles = []
    
    # Method 1: Look for formatted text
    for tag in section_soup.find_all(['b', 'strong', 'i', 'em', 'u']):
        text = tag.get_text(strip=True)
        if text and len(text) > 10 and not text.upper().startswith("ITEM"):
            titles.append(text)
    
    # Method 2: Look for bullet points and list items
    for li in section_soup.find_all('li'):
        text = li.get_text(strip=True)
        if text and len(text) > 10:
            titles.append(text)
    
    # Method 3: Look for short paragraphs
    paragraphs = section_soup.find_all('p')
    for p in paragraphs:
        text = p.get_text(strip=True)
        if text and 10 < len(text) < 200 and text.endswith('.'):
            titles.append(text)
    
    # Clean up titles
    clean_titles = []
    seen = set()
    for title in titles:
        cleaned = re.sub(r'\s+', ' ', title).strip()
        if cleaned and len(cleaned) > 10 and cleaned not in seen:
            clean_titles.append(cleaned)
            seen.add(cleaned)
    
    return clean_titles

def main():
    """Main function"""
    # Load the input file
    input_csv = "rasamplemini_rfdtitle_input.csv"
    output_csv = "rasamplemini_rfdtitle_output.csv"
    
    # Read CSV with dtype specification to avoid float conversion
    df = pd.read_csv(input_csv, dtype={'cik': str, 'filingyear': int})
    output_rows = []
    
    # Process each row
    for index, row in df.iterrows():
        cik = row['cik']
        filing_year = row['filingyear']
        print(f"Processing CIK: {cik}, Year: {filing_year}")
        
        # Get filing URL and date
        filing_url, filing_date = get_10k_url_and_filing_date(cik, filing_year)
        if not filing_url:
            # Add empty row if URL not found
            output_rows.append({
                'cik': cik,
                'filingyear': filing_year,
                'filingdate': '',
                'reportingdate': '',
                'rfdtitle': ''
            })
            continue
        
        # Get filing content
        response = requests.get(filing_url, headers=HEADERS)
        soup = BeautifulSoup(response.content, 'lxml')
        
        # Extract reporting date
        text = soup.get_text()
        reporting_date = extract_reporting_date(text, filing_year)
        
        # Find risk factor section
        risk_section = find_risk_factor_section(soup)
        
        # Extract risk factor titles
        if risk_section:
            risk_titles = extract_risk_factor_titles(risk_section)
            if risk_titles:
                for title in risk_titles:
                    output_rows.append({
                        'cik': cik,
                        'filingyear': filing_year,
                        'filingdate': filing_date,
                        'reportingdate': reporting_date,
                        'rfdtitle': title
                    })
            else:
                # Add empty row if no titles found
                output_rows.append({
                    'cik': cik,
                    'filingyear': filing_year,
                    'filingdate': filing_date,
                    'reportingdate': reporting_date,
                    'rfdtitle': ''
                })
        else:
            # Add empty row if section not found
            output_rows.append({
                'cik': cik,
                'filingyear': filing_year,
                'filingdate': filing_date,
                'reportingdate': reporting_date,
                'rfdtitle': ''
            })
        
        # Sleep to respect rate limits
        time.sleep(1)
    
    # Write output
    output_df = pd.DataFrame(output_rows)
    output_df.to_csv(output_csv, index=False)
    print(f"Output saved to {output_csv}")

if __name__ == '__main__':
    main()