from time import sleep

import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime

HEADERS = {
    'User-Agent': 's.devang@gwmail.gwu.edu',  # Replace with your email
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'www.sec.gov'
}


def get_10k_url_and_filing_date(cik, filing_year):
    cik = str(cik).zfill(10)
    start_date = f"{filing_year}0101"
    end_date = f"{filing_year}1231"
    base_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K&dateb={end_date}&datea={start_date}&owner=exclude&count=10"
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
                                        if '.htm' in href.lower() and 'Archives' in href:
                                            filing_url = "https://www.sec.gov" + href
                                            return filing_url, filing_date
        print(f"10-K URL not found for CIK: {cik}, Year: {filing_year}")
        return None, None
    except Exception as e:
        print(f"Error fetching 10-K URL for CIK {cik}: {e}")
        return None, None


def extract_reporting_date(text, filing_year):
    match = re.search(r'for the fiscal year ended ([A-Za-z]+ \d{1,2}, \d{4})', text, re.IGNORECASE)
    if match:
        try:
            return pd.to_datetime(match.group(1)).strftime('%Y-%m-%d')
        except Exception:
            pass
    
    # Try another common format
    match = re.search(r'for the year ended ([A-Za-z]+ \d{1,2}, \d{4})', text, re.IGNORECASE)
    if match:
        try:
            return pd.to_datetime(match.group(1)).strftime('%Y-%m-%d')
        except Exception:
            pass
            
    return f'{filing_year}-12-31'  # Default fallback


def extract_risk_factors(soup):
    """Extract risk factor titles using multiple methods to handle different document formats."""
    
    # Method 1: Look for section headers and bolded text
    risk_factors_section = get_risk_factors_section(soup)
    if risk_factors_section:
        # Get bold/strong elements that likely represent risk factor titles
        bold_elements = risk_factors_section.find_all(['b', 'strong'])
        titles = [tag.get_text().strip() for tag in bold_elements if len(tag.get_text().strip()) > 10]
        
        # Filter out non-title elements (too long or too short)
        titles = [title for title in titles if 10 <= len(title) <= 200]
        
        if titles:
            return titles
    
    # Method 2: Look for paragraphs with all caps or uppercase-heavy text in the risk section
    risk_text = get_full_risk_section_text(soup)
    if risk_text:
        paragraphs = risk_text.split('\n')
        potential_titles = []
        
        for p in paragraphs:
            p = p.strip()
            if 10 <= len(p) <= 200:  # Reasonable length for a title
                uppercase_ratio = sum(1 for c in p if c.isupper()) / max(1, len(p))
                if uppercase_ratio > 0.5:  # More than half uppercase
                    potential_titles.append(p)
        
        if potential_titles:
            return potential_titles
    
    # Method 3: Fall back to any paragraph that has bold nested elements
    all_paragraphs = soup.find_all(['p', 'div'])
    potential_titles = []
    
    for p in all_paragraphs:
        bold_elements = p.find_all(['b', 'strong'])
        for bold in bold_elements:
            text = bold.get_text().strip()
            if 10 <= len(text) <= 200:
                potential_titles.append(text)
    
    return potential_titles[:50]  # Limit to avoid returning too much noise


def get_risk_factors_section(soup):
    """Find the risk factors section using multiple pattern matching approaches."""
    # Look for standard headers
    headers = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'p', 'span', 'td'])
    
    for header in headers:
        text = header.get_text().lower().strip()
        if re.search(r'item\s*1a\.?\s*risk\s*factors', text):
            # Found the section header - now find the section content
            section = header.find_next_sibling()
            if section:
                return section
            
            # If no sibling, try the parent's next sibling
            parent = header.parent
            if parent:
                section = parent.find_next_sibling()
                if section:
                    return section
    
    # Try another approach - find the container that has 'risk factors' in it
    risk_containers = []
    for tag in soup.find_all(['div', 'td', 'section']):
        if re.search(r'item\s*1a\.?\s*risk\s*factors', tag.get_text().lower()):
            risk_containers.append(tag)
    
    # Choose the most appropriate container (smallest that still contains risk factors)
    if risk_containers:
        return min(risk_containers, key=lambda x: len(x.get_text()))
    
    return None


def get_full_risk_section_text(soup):
    """Extract the full text of the risk factors section."""
    text = soup.get_text()
    
    # Find the start of Item 1A
    start_match = re.search(r'Item\s*1A\.?\s*Risk\s*Factors', text, re.IGNORECASE)
    if not start_match:
        return None
    
    # Find the end (beginning of Item 1B or Item 2)
    end_pattern = r'Item\s*(1B|2)\.?\s*(Unresolved\s*Staff\s*Comments|Properties)'
    end_match = re.search(end_pattern, text[start_match.end():], re.IGNORECASE)
    
    if end_match:
        risk_section = text[start_match.end():start_match.end() + end_match.start()]
    else:
        # If no clear end found, take a reasonable amount of text (next 20000 chars)
        risk_section = text[start_match.end():start_match.end() + 20000]
    
    return risk_section


def main():
    input_csv_path = "rasamplemini_rfdtitle_9.csv"
    output_csv_path = "rasamplemini_rfdtitle_output_cl.csv"
    output_rows = []
    
    # Load input data
    df = pd.read_csv(input_csv_path, dtype={'cik': str})
    df.columns = df.columns.str.lower()
    
    print(f"Processing {len(df)} rows from input file...")
    
    for index, row in df.iterrows():
        cik = row['cik'].zfill(10)
        filing_year = int(row['filingyear'])
        
        print(f"Processing {index+1}/{len(df)}: CIK {cik}, Year {filing_year}")
        
        # Get 10-K URL
        tenk_url, filing_date = get_10k_url_and_filing_date(cik, filing_year)
        if not tenk_url:
            print(f"Skipping CIK: {cik}, Year: {filing_year} - URL not found")
            continue
        
        # Download and parse 10-K
        try:
            time.sleep(0.1)  # Respect SEC rate limits
            response = requests.get(tenk_url, headers=HEADERS)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'lxml')
            text = soup.get_text()
            
            # Extract reporting date
            reporting_date = extract_reporting_date(text, filing_year)
            
            # Extract risk factor titles
            risk_factor_titles = extract_risk_factors(soup)
            
            print(f"Found {len(risk_factor_titles)} risk factors for CIK {cik}, Year {filing_year}")
            
            if risk_factor_titles:
                for title in risk_factor_titles:
                    cleaned = re.sub(r'[\n\r\t\"\\]+', ' ', title).strip()
                    if cleaned:  # Only add non-empty titles
                        output_rows.append({
                            'cik': row['cik'],
                            'filingyear': filing_year,
                            'filingdate': filing_date,
                            'reportingdate': reporting_date,
                            'rfdtitle': cleaned
                        })
            else:
                # Add a placeholder row to show we processed this CIK but found no risk factors
                output_rows.append({
                    'cik': row['cik'],
                    'filingyear': filing_year,
                    'filingdate': filing_date,
                    'reportingdate': reporting_date,
                    'rfdtitle': "NO RISK FACTORS FOUND"
                })
            
        except Exception as e:
            print(f"Error processing CIK {cik}, Year {filing_year}: {e}")
            
        # Add a delay between companies to avoid hitting SEC rate limits
        time.sleep(1)
    
    # Output results
    if output_rows:
        output_df = pd.DataFrame(output_rows)
        output_df.to_csv(output_csv_path, index=False)
        print(f"Extraction completed. Found {len(output_rows)} risk factors across {len(df)} filings.")
        print(f"Output saved to {output_csv_path}")
    else:
        print("No risk factors found for any company. Check the error messages above.")


if __name__ == '__main__':
    main()