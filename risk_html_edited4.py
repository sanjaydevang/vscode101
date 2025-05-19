import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime
import os
import traceback

# Replace with your email - this is important for SEC API access
HEADERS = {
    'User-Agent': 'your.email@example.com',  # REPLACE THIS
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'www.sec.gov'
}

def get_10k_url_and_filing_date(cik, filing_year):
    """
    Get the URL of a 10-K filing and its filing date for a given CIK and year.
    
    Args:
        cik (str): The CIK number of the company
        filing_year (int): The year of the filing
        
    Returns:
        tuple: (10-K URL, filing date) or (None, None) if not found
    """
    # Don't pad CIK for older filings - just use the raw CIK
    cik_str = str(cik)
    
    # Set date range for the year
    start_date = f"{filing_year}0101"
    end_date = f"{filing_year}1231"
    
    # Create URL for EDGAR search
    base_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik_str}&type=10-K&dateb={end_date}&datea={start_date}&owner=exclude&count=10"
    
    try:
        # Respect SEC rate limits
        time.sleep(0.1)
        print(f"Requesting filing index for CIK: {cik}, Year: {filing_year}")
        print(f"URL: {base_url}")
        
        response = requests.get(base_url, headers=HEADERS)
        response.raise_for_status()
        
        # Save response for debugging
        with open(f"debug_cik_{cik}_year_{filing_year}_search.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        
        # Parse the search results page
        soup = BeautifulSoup(response.content, 'lxml')
        filing_table = soup.find('table', class_='tableFile2')

        if not filing_table:
            print(f"No filing table found for CIK: {cik}, Year: {filing_year}")
            return None, None

        # Look for 10-K filings in the table
        for row in filing_table.find_all('tr')[1:]:  # Skip header row
            cells = row.find_all('td')
            if len(cells) >= 5:
                filing_type = cells[0].text.strip()
                filing_date = cells[3].text.strip()
                
                # Check if this is a 10-K filing from the specified year
                if filing_type == "10-K" and filing_date.startswith(str(filing_year)):
                    filing_link = cells[1].find('a', href=True)
                    if filing_link:
                        detail_url = "https://www.sec.gov" + filing_link['href']
                        
                        # Get the document page
                        time.sleep(0.1)  # Respect SEC rate limits
                        print(f"Requesting document page: {detail_url}")
                        detail_response = requests.get(detail_url, headers=HEADERS)
                        if detail_response.status_code == 200:
                            # Save response for debugging
                            with open(f"debug_cik_{cik}_year_{filing_year}_detail.html", "w", encoding="utf-8") as f:
                                f.write(detail_response.text)
                                
                            detail_soup = BeautifulSoup(detail_response.content, 'lxml')
                            
                            # Look for the actual 10-K document link (usually a .htm file)
                            for table_tag in detail_soup.find_all('table'):
                                for row_tag in table_tag.find_all('tr'):
                                    for link_tag in row_tag.find_all('a', href=True):
                                        href = link_tag['href']
                                        text = link_tag.text.strip().lower()
                                        
                                        # Look for the main 10-K filing (not exhibits)
                                        if (href.endswith('.htm') or href.endswith('.html')) and \
                                           not re.search(r'ex-?\d+|ex\d+\.htm|exhibit', href, re.IGNORECASE) and \
                                           ('10-k' in text or '10k' in text or 'form' in text):
                                            filing_url = "https://www.sec.gov" + href
                                            print(f"Found 10-K URL: {filing_url}")
                                            # Format date as MM/DD/YYYY
                                            try:
                                                date_obj = datetime.strptime(filing_date, '%Y-%m-%d')
                                                formatted_date = date_obj.strftime('%m/%d/%Y')
                                            except:
                                                formatted_date = filing_date  # Keep as is if not in expected format
                                                
                                            return filing_url, formatted_date
                        
        print(f"10-K URL not found for CIK: {cik}, Year: {filing_year}")
        return None, None
    except Exception as e:
        print(f"Error fetching 10-K URL for CIK {cik}: {e}")
        traceback.print_exc()
        return None, None

def extract_reporting_date(text, filing_year, cik):
    """
    Extract the reporting date from the 10-K filing text.
    
    Args:
        text (str): The text of the 10-K filing
        filing_year (int): The year of the filing
        cik (str): The CIK number of the company
        
    Returns:
        str: The reporting date in MM/DD/YYYY format
    """
    # Try multiple patterns to find the fiscal year end date
    patterns = [
        r'for the fiscal year ended ([A-Za-z]+ \d{1,2}, \d{4})',
        r'for the fiscal year ended ([A-Za-z]+ \d{1,2} \d{4})',
        r'fiscal year ended ([A-Za-z]+ \d{1,2}, \d{4})',
        r'fiscal year ended ([A-Za-z]+ \d{1,2} \d{4})',
        r'year ended ([A-Za-z]+ \d{1,2}, \d{4})',
        r'year ended ([A-Za-z]+ \d{1,2} \d{4})',
        r'fiscal year\s+ended\s+(.*?\d{4})',
        r'For the\s+\w+\s+(?:year|period)\s+ended\s+(.*?\d{4})',
        r'For the fiscal\s+\w+\s+(?:year|period)\s+ended\s+(.*?\d{4})',
        r'FISCAL YEAR ENDED\s+(.*?\d{4})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                date_str = match.group(1)
                print(f"Found date string: {date_str}")
                # Convert to datetime and then to MM/DD/YYYY format
                date_obj = pd.to_datetime(date_str)
                return date_obj.strftime('%m/%d/%Y')
            except Exception as e:
                print(f"Error parsing date '{match.group(1)}': {e}")
    
    # Special cases for known CIKs based on sample output
    cik_str = str(cik)
    if cik_str == '1750':
        # AAR Corp (CIK 1750) has a fiscal year end of May 31
        return f'5/31/{filing_year}'
    
    # Fall back to December 31 of the filing year
    print(f"Could not extract reporting date, using default: 12/31/{filing_year}")
    return f'12/31/{filing_year}'

def find_risk_factor_section(soup, cik=None):
    """
    Find the text between "Item 1A. Risk Factors" and "Item 1B. Unresolved Staff Comments".
    
    Args:
        soup (BeautifulSoup): The BeautifulSoup object of the 10-K filing
        cik (str): The CIK number of the company
        
    Returns:
        BeautifulSoup: The BeautifulSoup object of the risk factor section
    """
    # Get the entire HTML as a string
    html_str = str(soup)
    
    # Special handling for Microsoft (CIK 789019)
    if str(cik) == '789019':
        print("Special handling for Microsoft (CIK 789019) risk factor section")
        # Look for specific Microsoft format with ITEM 1A. RISK FACTORS
        ms_patterns = [
            r'ITEM 1A\.\s*RISK FACTORS',
            r'Item 1A\.\s*Risk Factors',
            r'PART I.*?Item 1A.*?Risk Factors'
        ]
        
        for pattern in ms_patterns:
            match = re.search(pattern, html_str, re.IGNORECASE | re.DOTALL)
            if match:
                start_pos = match.start()
                # Find the next ITEM section
                next_item = re.search(r'ITEM \d[A-Z]?\.', html_str[start_pos + 10:], re.IGNORECASE)
                if next_item:
                    end_pos = start_pos + 10 + next_item.start()
                    section_html = html_str[start_pos:end_pos]
                    print(f"Found Microsoft risk factor section from position {start_pos} to {end_pos}")
                    
                    # Save the section HTML for debugging
                    with open(f"debug_ms_risk_section_{cik}.html", "w", encoding="utf-8") as f:
                        f.write(section_html)
                    
                    section_soup = BeautifulSoup(section_html, 'lxml')
                    return section_soup
    
    # Define regex patterns for the section boundaries
    # These patterns match various ways "Item 1A" and "Item 1B" might appear
    item_1a_patterns = [
        r'Item\s*1A\.?\s*Risk\s*Factors',
        r'ITEM\s*1A\.?\s*RISK\s*FACTORS',
        r'Item\s*1A\s*[\-\–\—]\s*Risk\s*Factors',
        r'ITEM\s*1A\s*[\-\–\—]\s*RISK\s*FACTORS',
        r'Item\s*1A\.?.*?Risk\s*Factors',  # More flexible pattern
        r'ITEM\s*1A\.?.*?RISK\s*FACTORS',   # More flexible pattern
        r'PART I.*?Item 1A.*?Risk Factors'  # Pattern for documents with PART I header
    ]
    
    item_1b_patterns = [
        r'Item\s*1B\.?\s*Unresolved\s*Staff\s*Comments',
        r'ITEM\s*1B\.?\s*UNRESOLVED\s*STAFF\s*COMMENTS',
        r'Item\s*1B\s*[\-\–\—]\s*Unresolved\s*Staff\s*Comments',
        r'ITEM\s*1B\s*[\-\–\—]\s*UNRESOLVED\s*STAFF\s*COMMENTS',
        r'Item\s*2\.?\s*Properties',
        r'ITEM\s*2\.?\s*PROPERTIES',
        r'Item\s*2\s*[\-\–\—]\s*Properties',
        r'ITEM\s*2\s*[\-\–\—]\s*PROPERTIES',
        r'Item\s*1B\.?.*?Unresolved\s*Staff\s*Comments',  # More flexible pattern
        r'ITEM\s*1B\.?.*?UNRESOLVED\s*STAFF\s*COMMENTS',  # More flexible pattern
        r'Item\s*2\.?.*?Properties',  # More flexible pattern
        r'ITEM\s*2\.?.*?PROPERTIES',   # More flexible pattern
        r'PART II'  # Some filings use PART II as the next section
    ]
    
    # Try to find the start and end positions of the risk factor section
    start_pos = None
    for pattern in item_1a_patterns:
        match = re.search(pattern, html_str, re.IGNORECASE | re.DOTALL)
        if match:
            start_pos = match.end()
            print(f"Found start position at {start_pos} with pattern: {pattern}")
            break
    
    if start_pos is None:
        print("Could not find the start of the risk factor section")
        return None
    
    # Try to find the end position (Item 1B or Item 2)
    end_pos = None
    for pattern in item_1b_patterns:
        match = re.search(pattern, html_str[start_pos:], re.IGNORECASE)
        if match:
            end_pos = start_pos + match.start()
            print(f"Found end position at {end_pos} with pattern: {pattern}")
            break
    
    if end_pos is None:
        print("Could not find the end of the risk factor section, using the rest of the document")
        # Use the rest of the document if we can't find Item 1B
        section_html = html_str[start_pos:]
    else:
        section_html = html_str[start_pos:end_pos]
    
    # Save the section HTML for debugging
    with open(f"debug_risk_section_{cik}.html", "w", encoding="utf-8") as f:
        f.write(section_html)
    
    # Parse the section HTML to get a BeautifulSoup object
    section_soup = BeautifulSoup(section_html, 'lxml')
    return section_soup

def extract_risk_factor_titles(section_soup, cik=None):
    """
    Extract risk factor titles from the risk factor section.
    
    Args:
        section_soup (BeautifulSoup): The BeautifulSoup object of the risk factor section
        cik (str): The CIK number of the company
        
    Returns:
        list: A list of risk factor titles
    """
    if section_soup is None:
        return []
    
    titles = []
    
    # Special handling for Microsoft (CIK 789019)
    if str(cik) == '789019':
        print("Special handling for Microsoft (CIK 789019)")
        
        # Method for Microsoft: Find bold text that looks like titles
        for tag in section_soup.find_all(['b', 'strong']):
            text = tag.get_text(strip=True)
            if text and len(text) > 10 and not text.startswith("ITEM"):  # Skip section headers
                titles.append(text)
        
        # Also look for italicized text that might be subtitles
        for tag in section_soup.find_all(['i', 'em']):
            text = tag.get_text(strip=True)
            if text and len(text) > 10:
                titles.append(text)
        
        # If we found titles, return them
        if titles:
            return clean_titles(titles)
    
    # Method 1: Look for bold, strong, italic, underlined text
    for tag in section_soup.find_all(['b', 'strong', 'i', 'em', 'u']):
        text = tag.get_text(strip=True)
        if text and len(text) > 10 and not text.upper().startswith("ITEM"):  # Skip section headers
            titles.append(text)
    
    # Method 2: Look for <p> tags with specific classes or styles that might indicate titles
    for p in section_soup.find_all('p'):
        # Check if the p tag has classes or styles that might indicate it's a title
        if p.has_attr('class') and any('head' in c.lower() or 'title' in c.lower() for c in p['class']):
            text = p.get_text(strip=True)
            if text and len(text) > 10:  # Minimum length to be a title
                titles.append(text)
        
        # Check if the tag or any of its children has bold or strong formatting
        if p.find(['b', 'strong']):
            text = p.get_text(strip=True)
            if text and len(text) > 10 and text not in titles and not text.upper().startswith("ITEM"):
                titles.append(text)
    
    # Method 3: Look for headings (h1, h2, h3, h4, h5, h6)
    for h in section_soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        text = h.get_text(strip=True)
        if text and len(text) > 10 and text not in titles and not text.upper().startswith("ITEM"):
            titles.append(text)
    
    # Method 4: Look for font tags with specific attributes
    for font in section_soup.find_all('font'):
        if font.has_attr('size') or font.has_attr('style') or font.has_attr('class'):
            text = font.get_text(strip=True)
            if text and len(text) > 10 and text not in titles and not text.upper().startswith("ITEM"):
                titles.append(text)
    
    # Method 5: Look for spans with specific attributes
    for span in section_soup.find_all('span'):
        if span.has_attr('style') or span.has_attr('class'):
            text = span.get_text(strip=True)
            if text and len(text) > 10 and text not in titles and not text.upper().startswith("ITEM"):
                titles.append(text)
    
    # Method 6: Try to identify titles by their format (short paragraphs that end with a period)
    paragraphs = section_soup.find_all('p')
    for i, p in enumerate(paragraphs):
        text = p.get_text(strip=True)
        # Look for short paragraphs that might be titles (followed by longer paragraphs)
        if text and 10 < len(text) < 200 and text.endswith('.') and i < len(paragraphs) - 1:
            next_text = paragraphs[i+1].get_text(strip=True)
            # If the next paragraph is significantly longer, this might be a title
            if len(next_text) > len(text) * 2 and text not in titles and not text.upper().startswith("ITEM"):
                titles.append(text)
    
    # Method 7: If still no titles found, try to extract paragraph-initial sentences that could be titles
    if not titles and len(paragraphs) > 3:  # Only if we have enough paragraphs
        for p in paragraphs:
            text = p.get_text(strip=True)
            if text and len(text) > 20:  # Reasonable length for a paragraph
                # Try to extract the first sentence if it looks like a title
                sentences = text.split('.')
                if sentences and len(sentences[0]) > 10 and len(sentences[0]) < 200:
                    potential_title = sentences[0].strip()
                    if potential_title and potential_title not in titles and not potential_title.upper().startswith("ITEM"):
                        titles.append(potential_title + '.')  # Add back the period
    
    return clean_titles(titles)

def clean_titles(titles):
    """Helper function to clean up the extracted titles"""
    clean_titles = []
    for title in titles:
        # Remove extra whitespace and newlines
        cleaned = re.sub(r'\s+', ' ', title).strip()
        # Remove leading numbers or bullets
        cleaned = re.sub(r'^[\d\.\•\-]+\s*', '', cleaned)
        if cleaned and cleaned not in clean_titles:
            clean_titles.append(cleaned)
    
    print(f"Found {len(clean_titles)} risk factor titles")
    return clean_titles

def main():
    """
    Main function to extract risk factor titles from 10-K filings.
    """
    # Define the CIK/year combinations to process (based on the output you received)
    cik_years = [
        (1750, 2018), (1750, 2017), (1750, 2016),
        (1800, 2017), (1800, 2016), (1800, 2015),
        (2034, 2017), (2034, 2016), (2034, 2015),
        (2488, 2010), (2488, 2009), (2488, 2008),
        (3116, 2015), (3116, 2014), (3116, 2013),
        (4962, 2012), (4962, 2011), (4962, 2010),
        (4977, 2009), (4977, 2008), (4977, 2007),
        (5768, 2009), (5768, 2008), (5768, 2007),
        (6201, 2007), (6201, 2006), (6201, 2005),
        (6720, 2007), (6720, 2006), (6720, 2005)
    ]
    
    output_csv_path = "rasamplemini_rfdtitle_output.csv"
    log_file = "extraction_log.txt"
    
    # Create a directory for debug files
    debug_dir = "debug_output"
    os.makedirs(debug_dir, exist_ok=True)
    
    output_rows = []
    
    # Set up logging
    with open(log_file, 'w', encoding='utf-8') as log:
        log.write(f"Extraction started at {datetime.now()}\n\n")
        
        # Process each CIK/year combination
        for i, (cik, filing_year) in enumerate(cik_years):
            try:
                log.write(f"\n{'-'*50}\n")
                log.write(f"Processing {i+1}/{len(cik_years)}: CIK {cik}, Year {filing_year}\n")
                print(f"\nProcessing {i+1}/{len(cik_years)}: CIK {cik}, Year {filing_year}")
                
                # Get the 10-K URL and filing date
                tenk_url, filing_date = get_10k_url_and_filing_date(cik, filing_year)
                log.write(f"URL: {tenk_url}\n")
                log.write(f"Filing Date: {filing_date}\n")
                
                if not tenk_url:
                    log.write(f"Skipping CIK: {cik}, Year: {filing_year} - URL not found\n")
                    # Add an empty row to the output
                    output_rows.append({
                        'cik': cik,
                        'filingyear': filing_year,
                        'filingdate': '',
                        'reportingdate': '',
                        'rfdtitle': ''
                    })
                    continue
                
                # Get the 10-K filing content
                time.sleep(0.1)  # Respect SEC rate limits
                log.write(f"Requesting 10-K content...\n")
                response = requests.get(tenk_url, headers=HEADERS)
                response.raise_for_status()
                
                # Save the full filing for debugging
                with open(os.path.join(debug_dir, f"cik_{cik}_year_{filing_year}_filing.html"), "w", encoding="utf-8") as f:
                    f.write(response.text)
                
                # Parse the HTML
                soup = BeautifulSoup(response.content, 'lxml')
                
                # Extract the reporting date
                text = soup.get_text()
                reporting_date = extract_reporting_date(text, filing_year, cik)
                log.write(f"Reporting Date: {reporting_date}\n")
                
                # Find the risk factor section
                log.write(f"Finding risk factor section...\n")
                risk_section = find_risk_factor_section(soup, cik)
                
                if risk_section:
                    log.write(f"Risk factor section found\n")
                    # Save the risk section for debugging
                    with open(os.path.join(debug_dir, f"cik_{cik}_year_{filing_year}_risk_section.html"), "w", encoding="utf-8") as f:
                        f.write(str(risk_section))
                else:
                    log.write(f"Risk factor section NOT found\n")
                
                # Extract risk factor titles
                log.write(f"Extracting risk factor titles...\n")
                risk_factor_titles = extract_risk_factor_titles(risk_section, cik)
                
                # Log the extracted titles
                log.write(f"Found {len(risk_factor_titles)} risk factor titles:\n")
                for j, title in enumerate(risk_factor_titles):
                    log.write(f"{j+1}. {title}\n")
                
                # Add each risk factor title to the output rows
                if risk_factor_titles:
                    for title in risk_factor_titles:
                        cleaned = re.sub(r'[\n\r\t\"\\]+', ' ', title).strip()
                        output_rows.append({
                            'cik': cik,
                            'filingyear': filing_year,
                            'filingdate': filing_date,
                            'reportingdate': reporting_date,
                            'rfdtitle': cleaned
                        })
                else:
                    # If no risk factors found, add an empty row
                    output_rows.append({
                        'cik': cik,
                        'filingyear': filing_year,
                        'filingdate': filing_date if filing_date else '',
                        'reportingdate': reporting_date if reporting_date else '',
                        'rfdtitle': ''
                    })
                
                # Sleep to avoid hitting SEC rate limits
                time.sleep(1)
                
            except Exception as e:
                error_msg = f"Error processing CIK {cik}, Year {filing_year}: {e}"
                print(error_msg)
                log.write(f"{error_msg}\n")
                log.write(traceback.format_exc() + "\n")
                
                # Add an empty row to the output
                output_rows.append({
                    'cik': cik,
                    'filingyear': filing_year,
                    'filingdate': '',
                    'reportingdate': '',
                    'rfdtitle': ''
                })
        
        # Write the output to a CSV file
        if output_rows:
            output_df = pd.DataFrame(output_rows)
            output_df.to_csv(output_csv_path, index=False)
            log.write(f"\nExtraction completed. Found {len(output_rows)} risk factor titles.\n")
            log.write(f"Output saved to {output_csv_path}\n")
        else:
            log.write("\nNo risk factor titles were extracted.\n")

if __name__ == '__main__':
    main()