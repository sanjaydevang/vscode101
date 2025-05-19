# Mock data for testing when SEC access fails
MOCK_RISK_TITLES = [
    "Our business is subject to cybersecurity risks",
    "We face significant competition in our industry",
    "Changes in regulations could adversely affect our business",
    "We depend on key personnel",
    "We may not be able to protect our intellectual property",
    "Our international operations expose us to various risks",
    "We may face difficulties in implementing new systems",
    "Economic downturns could adversely affect our revenue",
    "Our results may fluctuate due to seasonality",
    "We may be subject to litigation and regulatory proceedings"
]

def create_mock_data(cik, filing_year):
    """
    Create mock risk factor data for testing or when SEC access fails.
    
    Args:
        cik (str): The CIK number of the company
        filing_year (int): The year of the filing
    
    Returns:
        list: List of dictionaries containing mock risk factor data
    """
    results = []
    mock_filing_date = f"{filing_year}-06-30"
    mock_reporting_date = f"{filing_year}-12-31"
    
    # Use 5-7 random risk titles from the mock list
    import random
    num_titles = random.randint(5, 7)
    selected_titles = random.sample(MOCK_RISK_TITLES, num_titles)
    
    for title in selected_titles:
        results.append({
            'CIK': cik,
            'Filing Year': filing_year,
            'Filing Date': mock_filing_date,
            'Reporting Date': mock_reporting_date,
            'RFDTitle': f"MOCK_DATA: {title}"
        })
    
    return results

def process_filing(cik, filing_year, use_mock_on_fail=True):
    """
    Process a single 10-K filing to extract risk factor titles.
    
    Args:
        cik (str): The CIK number of the company
        filing_year (int): The year of the filing
        use_mock_on_fail (bool): Whether to create mock data when SEC access fails
    
    Returns:
        list: List of dictionaries containing extracted information
    """
    results = []
    
    # Remove any decimal point from CIK
    if isinstance(cik, (float, str)) and '.' in str(cik):
        cik = str(cik).split('.')[0]
    
    # Find the 10-K filing URL and filing date
    filing_url, filing_date = find_10k_filing_url(cik, filing_year)
    if not filing_url or not filing_date:
        logging.error(f"Could not find 10-K filing for CIK {cik} in {filing_year}")
        if use_mock_on_fail:
            logging.info(f"Creating mock data for CIK {cik} in {filing_year}")
            return create_mock_data(cik, filing_year)
        else:
            # Create a placeholder entry with empty risk titles
            results.append({
                'CIK': cik,
                'Filing Year': filing_year,
                'Filing Date': '',
                'Reporting Date': '',
                'RFDTitle': 'NO_DATA_FOUND'
            })
            return results
    
    logging.info(f"Found 10-K filing for CIK {cik} in {filing_year}, filed on {filing_date}")
    
    # Download the filing content
    response = sec_api_request(filing_url)
    if not response:
        # Create a placeholder entry with empty risk titles
        if use_mock_on_fail:
            logging.info(f"Creating mock data for CIK {cik} in {filing_year}")
            return create_mock_data(cik, filing_year)
        else:
            results.append({
                'CIK': cik,
                'Filing Year': filing_year,
                'Filing Date': filing_date,
                'Reporting Date': '',
                'RFDTitle': 'DOWNLOAD_FAILED'
            })
            return results
    
    filing_text = response.text
    
    # Extract the reporting date
    reporting_date = extract_reporting_date(filing_text)
    if not reporting_date:
        logging.warning(f"Could not extract reporting date for CIK {cik} in {filing_year}")
        # If no reporting date found, use December 31st of the filing year as a fallback
        reporting_date = f"{filing_year}-12-31"
    
    # Extract the risk factors section
    risk_section = extract_risk_factors_section(filing_text)
    if not risk_section:
        logging.error(f"Could not extract risk factors section for CIK {cik} in {filing_year}")
        if use_mock_on_fail:
            logging.info(f"Creating mock data for CIK {cik} in {filing_year}")
            return create_mock_data(cik, filing_year)
        else:
            # Create a placeholder entry with empty risk titles
            results.append({
                'CIK': cik,
                'Filing Year': filing_year,
                'Filing Date': filing_date,
                'Reporting Date': reporting_date,
                'RFDTitle': 'NO_RISK_SECTION_FOUND'
            })
            return results
    
    # First try to extract titles from HTML
    risk_titles = extract_risk_factor_titles_html(risk_section)
    
    # If HTML parsing doesn't yield good results, try text-based extraction
    if len(risk_titles) < 5:  # Arbitrary threshold
        logging.info(f"Few titles found via HTML parsing ({len(risk_titles)}), trying text-based extraction")
        text_titles = extract_risk_factor_titles_text(risk_section)
        # If text extraction found more titles, use those instead
        if len(text_titles) > len(risk_titles):
            risk_titles = text_titles
    
    logging.info(f"Extracted {len(risk_titles)} risk factor titles for CIK {cik} in {filing_year}")
    
    # If no risk titles were found, add a placeholder or use mock data
    if not risk_titles:
        if use_mock_on_fail:
            logging.info(f"No risk titles found, creating mock data for CIK {cik} in {filing_year}")
            return create_mock_data(cik, filing_year)
        else:
            results.append({
                'CIK': cik,
                'Filing Year': filing_year,
                'Filing Date': filing_date,
                'Reporting Date': reporting_date,
                'RFDTitle': 'NO_RISK_TITLES_FOUND'
            })
            return results
    
    # Create result entries
    for title in risk_titles:
        results.append({
            'CIK': cik,
            'Filing Year': filing_year,
            'Filing Date': filing_date,
            'Reporting Date': reporting_date,
            'RFDTitle': title
        })
    
    return results

import requests
import re
import os
import time
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
import logging
from urllib.parse import urljoin

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("risk_factor_extraction.log"),
        logging.StreamHandler()
    ]
)

# Print initial debug info about columns
logging.info("Starting risk factor extraction script")

# Constants
SEC_ARCHIVE_URL = "https://www.sec.gov/Archives/"
EDGAR_SEARCH_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
USER_AGENT = "s.devang@gwmail.gwu.edu"  # Replace with your details
HEADERS = {'User-Agent': USER_AGENT}

# Rate limiting to comply with SEC guidelines
def sec_api_request(url):
    """Make a request to the SEC EDGAR API with appropriate rate limiting."""
    time.sleep(0.1)  # Wait 100ms between requests to comply with SEC guidelines
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            return response
        else:
            logging.error(f"Failed to fetch {url}, status code: {response.status_code}")
            return None
    except Exception as e:
        logging.error(f"Error fetching {url}: {str(e)}")
        return None

def find_10k_filing_url(cik, filing_year):
    """
    Find the 10-K filing URL for a given CIK and filing year.
    
    Args:
        cik (str): The CIK number of the company
        filing_year (int): The year to search for filings
    
    Returns:
        tuple: (filing_url, filing_date) or (None, None) if not found
    """
    # Remove any decimal point from CIK
    if isinstance(cik, (float, str)) and '.' in str(cik):
        cik = str(cik).split('.')[0]
    
    # Format CIK with leading zeros to 10 digits
    cik_padded = str(cik).zfill(10)
    
    # Set date range for the filing year
    start_date = f"{filing_year}0101"
    end_date = f"{filing_year}1231"
    
    # Construct search URL
    search_url = f"{EDGAR_SEARCH_URL}?CIK={cik}&type=10-K&dateb={end_date}&datea={start_date}&owner=exclude&count=100"
    
    logging.info(f"Searching for 10-K filings for CIK {cik} in {filing_year}")
    logging.info(f"Search URL: {search_url}")
    
    response = sec_api_request(search_url)
    
    if not response:
        logging.error(f"Failed to get response from SEC for CIK {cik} in {filing_year}")
        return None, None
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Check for "No matching Filings" message
    no_match_text = soup.find(text=re.compile("No matching Filings", re.IGNORECASE))
    if no_match_text:
        logging.warning(f"SEC returned 'No matching Filings' for CIK {cik} in {filing_year}")
        return None, None
    
    # Find the table containing filing information
    filing_table = soup.find('table', class_='tableFile2')
    if not filing_table:
        logging.warning(f"No filing table found for CIK {cik} in {filing_year}")
        return None, None
    
    # Look for 10-K filings in the table
    for row in filing_table.find_all('tr')[1:]:  # Skip header row
        cells = row.find_all('td')
        if len(cells) >= 5:
            filing_type = cells[0].text.strip()
            filing_date = cells[3].text.strip()
            
            # Check if this is a 10-K filing
            if filing_type == "10-K":
                # Get the link to the filing detail page
                filing_link = cells[1].find('a', href=True)
                if filing_link:
                    detail_url = urljoin("https://www.sec.gov", filing_link['href'])
                    
                    # Get the filing detail page
                    detail_response = sec_api_request(detail_url)
                    if detail_response:
                        detail_soup = BeautifulSoup(detail_response.text, 'html.parser')
                        
                        # Find the link to the full text filing
                        for table_tag in detail_soup.find_all('table'):
                            for row_tag in table_tag.find_all('tr'):
                                if 'Complete submission text file' in row_tag.text:
                                    for link_tag in row_tag.find_all('a', href=True):
                                        filing_url = urljoin("https://www.sec.gov", link_tag['href'])
                                        return filing_url, filing_date
    
    logging.warning(f"No 10-K filing found for CIK {cik} in {filing_year}")
    return None, None

def extract_reporting_date(text):
    """
    Extract the fiscal year end (reporting date) from the 10-K text.
    
    Args:
        text (str): The text content of the 10-K filing
    
    Returns:
        str: The reporting date in YYYY-MM-DD format or None if not found
    """
    # Common patterns for fiscal year end dates in 10-K filings
    patterns = [
        r"fiscal\s+year\s+end(?:ed)?\s+(?:on)?\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
        r"for\s+the\s+(?:fiscal\s+)?year\s+end(?:ed)?\s+(?:on)?\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
        r"(?:as\s+of|ended|date)\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
        r"fiscal\s+year\s+end(?:ed)?\s+(?:on)?\s+(\d{1,2}/\d{1,2}/\d{4})",
        r"for\s+the\s+(?:fiscal\s+)?year\s+end(?:ed)?\s+(?:on)?\s+(\d{1,2}/\d{1,2}/\d{4})",
        r"(?:as\s+of|ended|date)\s+(\d{1,2}/\d{1,2}/\d{4})",
        r"fiscal\s+year\s+end(?:ed)?\s+(?:on)?\s+(\d{4}-\d{2}-\d{2})",
        r"for\s+the\s+(?:fiscal\s+)?year\s+end(?:ed)?\s+(?:on)?\s+(\d{4}-\d{2}-\d{2})",
        r"(?:as\s+of|ended|date)\s+(\d{4}-\d{2}-\d{2})"
    ]
    
    # Search in the first 10000 characters for better performance
    search_text = text[:10000]
    
    for pattern in patterns:
        matches = re.findall(pattern, search_text, re.IGNORECASE)
        if matches:
            try:
                date_str = matches[0].replace(',', '')
                # Try different date formats
                for fmt in ["%B %d %Y", "%m/%d/%Y", "%Y-%m-%d"]:
                    try:
                        reporting_date = datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
                        return reporting_date
                    except ValueError:
                        continue
            except Exception as e:
                logging.warning(f"Failed to parse reporting date: {matches[0]}, error: {str(e)}")
                continue
    
    # If no date found in patterns, try to find any date near fiscal year mentions
    fiscal_year_patterns = [
        r"fiscal\s+year\s+(\d{4})",
        r"for\s+the\s+year\s+ended\s+(\d{4})",
        r"fiscal\s+year\s+ended\s+(\d{4})"
    ]
    
    for pattern in fiscal_year_patterns:
        matches = re.findall(pattern, search_text, re.IGNORECASE)
        if matches:
            year = matches[0]
            # Default to December 31st of the fiscal year if only year is found
            return f"{year}-12-31"
    
    logging.warning("Could not extract reporting date from filing")
    return None

def extract_risk_factors_section(text):
    """
    Extract the "Item 1A. Risk Factors" section from the 10-K text.
    
    Args:
        text (str): The text content of the 10-K filing
    
    Returns:
        str: The extracted risk factors section or None if not found
    """
    # Various patterns for the beginning of Item 1A section
    start_patterns = [
        r"Item\s+1A\.?\s*Risk\s+Factors",
        r"ITEM\s+1A\.?\s*RISK\s+FACTORS",
        r"Item\s+1A\s*\.\s*Risk\s+Factors",
        r"ITEM\s+1A\s*\.\s*RISK\s+FACTORS"
    ]
    
    # Various patterns for the end of Item 1A section (beginning of next section)
    end_patterns = [
        r"Item\s+1B\.?\s*Unresolved\s+Staff\s+Comments",
        r"ITEM\s+1B\.?\s*UNRESOLVED\s+STAFF\s+COMMENTS",
        r"Item\s+2\.?\s*Properties",
        r"ITEM\s+2\.?\s*PROPERTIES",
        r"Item\s+1B\s*\.\s*Unresolved\s+Staff\s+Comments",
        r"ITEM\s+1B\s*\.\s*UNRESOLVED\s+STAFF\s+COMMENTS"
    ]
    
    # Try to find the start and end of the risk factors section
    start_match = None
    for pattern in start_patterns:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        if matches:
            start_match = matches[0]
            break
    
    if not start_match:
        logging.warning("Could not find the start of Item 1A. Risk Factors section")
        return None
    
    # Find the end of the section
    end_match = None
    for pattern in end_patterns:
        matches = list(re.finditer(pattern, text, re.IGNORECASE | re.DOTALL))
        if matches:
            # Find the first match that occurs after the start_match
            for match in matches:
                if match.start() > start_match.end():
                    end_match = match
                    break
            if end_match:
                break
    
    # Extract the section text
    if start_match and end_match:
        section_text = text[start_match.start():end_match.start()]
        return section_text
    elif start_match:
        # If we can't find the end, take a reasonable chunk after the start
        section_text = text[start_match.start():start_match.start() + 100000]  # Arbitrary large number
        logging.warning("Could not find the end of Item 1A section, taking a chunk of text")
        return section_text
    
    return None

def extract_risk_factor_titles_html(section_html):
    """
    Extract risk factor titles from HTML content based on formatting.
    
    Args:
        section_html (str): The HTML content of the risk factors section
    
    Returns:
        list: List of extracted risk factor titles
    """
    titles = []
    soup = BeautifulSoup(section_html, 'html.parser')
    
    # Look for common formatting patterns for risk factor titles
    
    # 1. Bold text that's likely a title
    for bold in soup.find_all(['b', 'strong']):
        text = bold.get_text().strip()
        # Only consider bold text that looks like a title (not too long, not too short)
        if 20 <= len(text) <= 200 and not text.endswith('.'):
            titles.append(text)
    
    # 2. Text in italics that might be titles
    for italic in soup.find_all(['i', 'em']):
        text = italic.get_text().strip()
        if 20 <= len(text) <= 200 and not text.endswith('.'):
            titles.append(text)
    
    # 3. Underlined text
    for underline in soup.find_all('u'):
        text = underline.get_text().strip()
        if 20 <= len(text) <= 200 and not text.endswith('.'):
            titles.append(text)
    
    # 4. Font tags with specific styles
    for font in soup.find_all('font'):
        if font.has_attr('style') and ('bold' in font['style'].lower() or 'weight' in font['style'].lower()):
            text = font.get_text().strip()
            if 20 <= len(text) <= 200 and not text.endswith('.'):
                titles.append(text)
    
    # 5. Headers
    for header in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        text = header.get_text().strip()
        if 20 <= len(text) <= 200 and not text.startswith('Item') and not text.endswith('.'):
            titles.append(text)
    
    # 6. Paragraphs with specific classes or styles indicating headers
    for p in soup.find_all('p'):
        if p.has_attr('class') and any('head' in cls.lower() for cls in p['class']):
            text = p.get_text().strip()
            if 20 <= len(text) <= 200 and not text.endswith('.'):
                titles.append(text)
        elif p.has_attr('style') and ('bold' in p['style'].lower() or 'weight' in p['style'].lower()):
            text = p.get_text().strip()
            if 20 <= len(text) <= 200 and not text.endswith('.'):
                titles.append(text)
    
    # Remove duplicates while preserving order
    unique_titles = []
    for title in titles:
        # Clean up the title - remove extra whitespace, newlines
        cleaned_title = re.sub(r'\s+', ' ', title).strip()
        if cleaned_title and cleaned_title not in unique_titles:
            unique_titles.append(cleaned_title)
    
    return unique_titles

def extract_risk_factor_titles_text(section_text):
    """
    Extract risk factor titles from plain text using pattern recognition.
    This is a fallback if HTML parsing doesn't yield good results.
    
    Args:
        section_text (str): The text content of the risk factors section
    
    Returns:
        list: List of extracted risk factor titles
    """
    titles = []
    
    # Common patterns for risk factor titles
    # 1. All caps phrases that might be titles
    all_caps_pattern = r'\n([A-Z][A-Z\s,\.\-&\'\(\)]{10,100})[^\n]*\n'
    all_caps_matches = re.findall(all_caps_pattern, section_text)
    
    # 2. Phrases that start with "Risk Factor:" or similar
    risk_phrase_pattern = r'(?:Risk(?:\s+Factor)?|Risk(?:-|\s+)Related)(?::|—|-)\s*([^\n\.]+)'
    risk_phrase_matches = re.findall(risk_phrase_pattern, section_text, re.IGNORECASE)
    
    # 3. Numbered or bulleted items that could be risk factors
    numbered_pattern = r'\n\s*(?:\d+\.|\•|\*)\s+([A-Z][^\n\.]{10,150})'
    numbered_matches = re.findall(numbered_pattern, section_text)
    
    # Combine all potential titles
    all_matches = all_caps_matches + risk_phrase_matches + numbered_matches
    
    # Clean and filter titles
    for match in all_matches:
        cleaned_title = re.sub(r'\s+', ' ', match).strip()
        if cleaned_title and 20 <= len(cleaned_title) <= 200 and cleaned_title not in titles:
            titles.append(cleaned_title)
    
    return titles

def main():
    """Main function to process all companies in the sample."""
    start_time = time.time()
    
    # Load the input data
    input_file = "rasamplemini_rfdtitle.csv"  # Update with your input file path
    output_file = "rasamplemini_rfdtitle_completed.csv"
    
    try:
        df = pd.read_csv(input_file)
        logging.info(f"Loaded input file with {len(df)} rows")
        
        # Print column names to debug
        logging.info(f"Column names in the CSV file: {df.columns.tolist()}")
        
        # Check and standardize column names (lowercase for case-insensitive matching)
        column_mapping = {}
        for col in df.columns:
            if col.lower() == 'cik':
                column_mapping[col] = 'CIK'
            elif 'filing' in col.lower() and 'year' in col.lower():
                column_mapping[col] = 'Filing Year'
        
        # Rename columns if mapping exists
        if column_mapping:
            df = df.rename(columns=column_mapping)
            logging.info(f"Renamed columns: {column_mapping}")
        
        # If column names are still different, try to guess them based on content
        if 'CIK' not in df.columns:
            # If there's a column that contains only numeric values around 1000-10000, it's likely CIK
            for col in df.columns:
                if df[col].dtype in ['int64', 'float64'] or (df[col].apply(lambda x: str(x).isdigit()).all() and df[col].nunique() > 1):
                    df = df.rename(columns={col: 'CIK'})
                    logging.info(f"Guessed column '{col}' as CIK based on content")
                    break
        
        if 'Filing Year' not in df.columns:
            # If there's a column that contains years (2016, 2017, 2018, etc.), it's likely Filing Year
            for col in df.columns:
                if df[col].dtype in ['int64', 'float64'] and df[col].min() >= 2000 and df[col].max() <= 2025:
                    df = df.rename(columns={col: 'Filing Year'})
                    logging.info(f"Guessed column '{col}' as Filing Year based on content")
                    break
        
        # Check if we have the required columns
        required_cols = ['CIK', 'Filing Year']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            logging.error(f"Missing required columns: {missing_cols}")
            logging.error(f"Available columns: {df.columns.tolist()}")
            
            # As a last resort, try to use columns by position
            if len(df.columns) >= 2:
                logging.warning("Attempting to use columns by position as a fallback")
                df = df.rename(columns={df.columns[0]: 'CIK', df.columns[1]: 'Filing Year'})
                logging.info(f"Renamed first column to 'CIK' and second column to 'Filing Year'")
    except Exception as e:
        logging.error(f"Error loading or processing input file: {str(e)}")
        return
    
    # Create a list to store all results
    all_results = []
    
    # Process each company in the sample
    for index, row in df.iterrows():
        try:
            cik = str(row['CIK']).strip()
            filing_year = int(row['Filing Year'])
            
            logging.info(f"Processing CIK {cik} for filing year {filing_year}")
            
            results = process_filing(cik, filing_year)
            all_results.extend(results)
            
            # Add a short delay between companies to avoid overloading the SEC server
            time.sleep(1)
        except Exception as e:
            logging.error(f"Error processing row {index}: {str(e)}")
            # Add placeholder entry for errors
            all_results.append({
                'CIK': row.get('CIK', 'UNKNOWN'),
                'Filing Year': row.get('Filing Year', 'UNKNOWN'),
                'Filing Date': '',
                'Reporting Date': '',
                'RFDTitle': f'ERROR: {str(e)}'
            })
            continue
    
    # Create empty output with headers if no results
    if not all_results:
        logging.warning("No results were extracted. Creating empty output file with headers.")
        all_results.append({
            'CIK': '',
            'Filing Year': '',
            'Filing Date': '',
            'Reporting Date': '',
            'RFDTitle': 'NO_DATA_FOUND'
        })
    
    # Convert results to DataFrame
    results_df = pd.DataFrame(all_results)
    
    # Save results
    try:
        results_df.to_csv(output_file, index=False)
        logging.info(f"Results saved to {output_file}")
        print(f"Output CSV file created: {output_file}")
    except Exception as e:
        logging.error(f"Error saving results: {str(e)}")
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    logging.info(f"Total time elapsed: {elapsed_time:.2f} seconds")
    print(f"Task completed in {elapsed_time:.2f} seconds. Extracted {len(all_results)} risk factor titles.")

if __name__ == "__main__":
    main()