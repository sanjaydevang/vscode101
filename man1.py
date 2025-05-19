import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
import os

# Replace with your email
HEADERS = {
    'User-Agent': 'your.email@example.com',  # REPLACE THIS
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'www.sec.gov'
}

# Create debug directory
if not os.path.exists('debug'):
    os.makedirs('debug')

def get_10k_url(cik, filing_year):
    """Get the 10-K filing URL for a given CIK and year"""
    cik_str = str(cik).zfill(10)
    filing_year = int(filing_year)
    
    # Create date range for search
    start_date = f"{filing_year-1}1201"  # From December of previous year
    end_date = f"{filing_year}1231"      # To December of filing year
    
    # Create EDGAR search URL
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik_str}&type=10-K&dateb={end_date}&datea={start_date}&owner=exclude&count=40"
    print(f"Searching: {url}")
    
    try:
        time.sleep(0.1)  # Respect SEC rate limits
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            print(f"Error: Status code {response.status_code}")
            return None, None

        # Save HTML for debugging
        with open(f"debug/search_{cik}_{filing_year}.html", "w", encoding="utf-8", errors='ignore') as f:
            f.write(response.text)
        
        # Parse HTML to find filing link
        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table', class_='tableFile2')
        
        if not table:
            print(f"No filing table found for CIK: {cik}, Year: {filing_year}")
            return None, None
        
        # Look for 10-K filings in the table
        for row in table.find_all('tr')[1:]:  # Skip header row
            cells = row.find_all('td')
            if len(cells) >= 4:
                filing_type = cells[0].text.strip()
                filing_date = cells[3].text.strip()
                
                # Check if this is a 10-K from the right year
                if filing_type == "10-K" and str(filing_year) in filing_date:
                    filing_link = cells[1].find('a', href=True)
                    if filing_link:
                        detail_url = "https://www.sec.gov" + filing_link['href']
                        print(f"Found filing page: {detail_url}")
                        
                        # Format filing date
                        try:
                            date_obj = pd.to_datetime(filing_date)
                            filing_date = date_obj.strftime('%m/%d/%Y')
                        except:
                            pass  # Keep original format if conversion fails
                        
                        # Get the filing detail page
                        time.sleep(0.1)
                        detail_response = requests.get(detail_url, headers=HEADERS)
                        detail_soup = BeautifulSoup(detail_response.content, 'html.parser')
                        
                        # Look for the actual 10-K document
                        for table_tag in detail_soup.find_all('table'):
                            for row_tag in table_tag.find_all('tr'):
                                for link_tag in row_tag.find_all('a', href=True):
                                    href = link_tag['href']
                                    if href.endswith('.htm') and not re.search(r'ex-?\d+|ex\d+\.htm', href, re.IGNORECASE):
                                        filing_url = "https://www.sec.gov" + href
                                        print(f"Found 10-K URL: {filing_url}")
                                        return filing_url, filing_date
        
        print(f"No 10-K URL found for CIK: {cik}, Year: {filing_year}")
        return None, None
    
    except Exception as e:
        print(f"Error during search: {e}")
        return None, None

def extract_risk_section(html, soup, cik, filing_year):
    """Extract the risk factor section from the filing"""
    # Different patterns to find risk factor section
    start_patterns = [
        r'Item\s*1A\.?\s*Risk\s*Factors',
        r'ITEM\s*1A\.?\s*RISK\s*FACTORS',
        r'Risk\s*Factors',
        r'RISK\s*FACTORS',
        r'Item\s*1A[\.\s]',
        r'ITEM\s*1A[\.\s]'
    ]
    
    end_patterns = [
        r'Item\s*1B',
        r'ITEM\s*1B',
        r'Item\s*2',
        r'ITEM\s*2',
        r'Unresolved\s+Staff\s+Comments',
        r'PART\s*II'
    ]
    
    # Try to find the section
    start_pos = None
    for pattern in start_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            start_pos = match.end()
            print(f"Found risk section start with pattern: {pattern}")
            break
    
    if start_pos is None:
        print(f"Could not find risk factor section for CIK {cik}, Year {filing_year}")
        return None
    
    # Find the end of the section
    end_pos = None
    for pattern in end_patterns:
        match = re.search(pattern, html[start_pos:], re.IGNORECASE)
        if match:
            end_pos = start_pos + match.start()
            break
    
    if end_pos is None:
        print("Could not find end of risk section, using fixed chunk")
        end_pos = start_pos + 100000  # Use a reasonable chunk
    
    # Extract and save the section
    section_html = html[start_pos:end_pos]
    with open(f"debug/risk_section_{cik}_{filing_year}.html", "w", encoding="utf-8", errors='ignore') as f:
        f.write(section_html)
    
    # Parse the section HTML
    return BeautifulSoup(section_html, 'html.parser')

def identify_risk_factors(section_soup, cik, filing_year):
    """
    Intelligently identify risk factor titles from the risk section
    """
    if section_soup is None:
        return []

    # Save section text for debugging
    section_text = section_soup.get_text()
    with open(f"debug/risk_section_text_{cik}_{filing_year}.txt", "w", encoding="utf-8", errors='ignore') as f:
        f.write(section_text)
    
    # We'll store potential risk factors here
    risk_factors = []
    
    # FIRST APPROACH: Find structured risk factors using bold formatting
    # This works for companies that use bold headers for risk factors
    bold_titles = []
    for tag in section_soup.find_all(['b', 'strong']):
        text = tag.get_text(strip=True)
        if text and len(text) > 15 and not text.upper().startswith("ITEM"):
            # Look for parent paragraph to get context
            parent = tag.find_parent('p')
            if parent:
                # Sometimes the full risk factor title includes text after the bold part
                full_text = parent.get_text(strip=True)
                # If the bold text is at the beginning of a paragraph, it's likely a title
                if full_text.startswith(text):
                    # Get the first sentence
                    match = re.search(r'^(.*?\.)', full_text)
                    if match:
                        title = match.group(1).strip()
                        if is_valid_risk_factor(title):
                            bold_titles.append(title)
                            print(f"Found bold title: {title[:50]}...")
                else:
                    if is_valid_risk_factor(text):
                        bold_titles.append(text)
                        print(f"Found bold title: {text[:50]}...")
            else:
                if is_valid_risk_factor(text):
                    bold_titles.append(text)
                    print(f"Found bold title: {text[:50]}...")
    
    # SECOND APPROACH: Handle special cases for different companies
    if cik == '4962':  # American Express
        print("Using special approach for American Express")
        # For American Express, look for complete sentences that discuss risks
        sentences = re.findall(r'([A-Z][^\.]+\.)(?:\s+[A-Z])', section_text)
        for sentence in sentences:
            sentence = sentence.strip()
            if is_valid_risk_factor(sentence) and len(sentence.split()) >= 7:
                if sentence not in bold_titles:
                    bold_titles.append(sentence)
                    print(f"Found AMEX sentence: {sentence[:50]}...")
    
    # If we found good titles using bold formatting, use those
    if bold_titles:
        risk_factors.extend(bold_titles)
    else:
        # THIRD APPROACH: Find paragraphs that look like risk factors
        # This approach finds paragraphs that introduce risks
        paragraphs = section_soup.find_all('p')
        for p in paragraphs:
            text = p.get_text(strip=True)
            if is_paragraph_risk_factor(text):
                # Extract just the first sentence if it's a long paragraph
                match = re.search(r'^(.*?\.)', text)
                if match:
                    title = match.group(1).strip()
                    if is_valid_risk_factor(title) and len(title.split()) >= 5:
                        risk_factors.append(title)
                        print(f"Found paragraph risk: {title[:50]}...")
    
    # FOURTH APPROACH: if we still don't have enough risk factors, look for risk phrases
    if len(risk_factors) < 5:
        risk_phrases = find_risk_phrases(section_text)
        for phrase in risk_phrases:
            if phrase not in risk_factors and is_valid_risk_factor(phrase) and len(phrase.split()) >= 5:
                risk_factors.append(phrase)
                print(f"Found risk phrase: {phrase[:50]}...")
    
    # Clean and deduplicate risk factors
    clean_factors = []
    seen = set()
    
    for factor in risk_factors:
        # Clean up the factor
        cleaned = re.sub(r'\s+', ' ', factor).strip()
        
        # Only include if it's a good title and hasn't been seen before
        if (cleaned and cleaned not in seen and 
            not cleaned.upper().startswith("ITEM") and 
            len(cleaned.split()) >= 5):
            clean_factors.append(cleaned)
            seen.add(cleaned)
    
    print(f"Found {len(clean_factors)} valid risk factors")
    return clean_factors

def is_valid_risk_factor(text):
    """
    Check if a piece of text looks like a valid risk factor title
    """
    # Risk factors usually mention negative outcomes or concerns
    risk_words = ['risk', 'risks', 'adverse', 'impact', 'affect', 'failure', 'unable', 
                 'not', 'negative', 'loss', 'damage', 'subject to', 'litigation',
                 'could', 'may', 'might', 'regulatory', 'decline', 'decrease',
                 'competition', 'competitive', 'challenges', 'difficult', 'uncertain',
                 'volatility', 'fluctuation']
    
    # Check for common risk factor patterns
    text_lower = text.lower()
    has_risk_word = any(word in text_lower for word in risk_words)
    
    # Risk factors typically end with a period
    ends_properly = text.strip().endswith('.')
    
    # Risk factors should be reasonably long but not too long
    good_length = 10 < len(text.split()) < 50
    
    return has_risk_word and ends_properly and good_length

def is_paragraph_risk_factor(text):
    """
    Check if a paragraph is introducing a risk factor
    """
    # Paragraphs that start with these phrases often introduce risk factors
    starter_phrases = ['we face', 'we are subject', 'our business', 'our success',
                      'we may', 'we cannot', 'we depend', 'we have', 'if we', 
                      'the company', 'changes in', 'failure to']
    
    text_lower = text.lower()
    
    # Check if paragraph starts with a risk-introducing phrase
    starts_with_phrase = any(text_lower.startswith(phrase) for phrase in starter_phrases)
    
    # Check if paragraph contains risk-related words
    risk_words = ['risk', 'risks', 'adverse', 'impact', 'affect', 'failure', 'unable', 
                 'not', 'negative', 'loss', 'damage', 'subject to', 'litigation',
                 'could', 'may', 'might', 'regulatory']
    
    has_risk_word = any(word in text_lower for word in risk_words)
    
    # Paragraph should not be too short or too long
    good_length = 20 < len(text) < 1000
    
    return (starts_with_phrase or has_risk_word) and good_length

def find_risk_phrases(text):
    """
    Find phrases that appear to be risk factors based on patterns
    """
    risk_phrases = []
    
    # Pattern 1: Sentences starting with risk-introducing words
    for starter in ['We face', 'We are subject', 'Our business', 'Our ability',
                   'We may', 'We cannot', 'We depend', 'Our success', 'If we',
                   'The Company', 'Changes in', 'Failure to']:
        # Find sentences starting with the phrase and ending with a period
        pattern = f'{re.escape(starter)}[^\.]+\.'
        matches = re.findall(pattern, text, re.IGNORECASE)
        risk_phrases.extend(matches)
    
    # Pattern 2: Sentences containing strong risk words
    for risk_word in ['significant risk', 'material adverse', 'substantial risk',
                     'negatively impact', 'adversely affect', 'substantial harm',
                     'serious consequences', 'adverse effect', 'significant negative']:
        pattern = f'[A-Z][^\.]*{re.escape(risk_word)}[^\.]+\.'
        matches = re.findall(pattern, text, re.IGNORECASE)
        risk_phrases.extend(matches)
    
    return risk_phrases

def get_reporting_date(text, filing_year):
    """Extract the reporting date from the 10-K text"""
    # Try multiple patterns for fiscal year end
    patterns = [
        r'for the fiscal year ended ([A-Za-z]+ \d{1,2}, \d{4})',
        r'for the fiscal year ended ([A-Za-z]+ \d{1,2} \d{4})',
        r'fiscal year ended ([A-Za-z]+ \d{1,2}, \d{4})',
        r'fiscal year ended ([A-Za-z]+ \d{1,2} \d{4})',
        r'year ended ([A-Za-z]+ \d{1,2}, \d{4})',
        r'year ended ([A-Za-z]+ \d{1,2} \d{4})',
        r'period ended ([A-Za-z]+ \d{1,2}, \d{4})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                date_str = match.group(1)
                date_obj = pd.to_datetime(date_str)
                return date_obj.strftime('%m/%d/%Y')
            except:
                pass
    
    # If no date found, use December 31 of previous year
    return f'12/31/{int(filing_year)-1}'

def main():
    """Main function to process the input CSV"""
    # Input and output files
    input_csv = "rasamplemini_rfdtitle_input.csv"
    output_csv = "rasamplemini_rfdtitle_output.csv"
    
    # Read the input CSV
    df = pd.read_csv(input_csv, dtype={'cik': str, 'filingyear': str})
    output_rows = []
    
    # Process each row
    for _, row in df.iterrows():
        cik = row['cik']
        filing_year = row['filingyear']
        print(f"\nProcessing CIK: {cik}, Year: {filing_year}")
        
        # Get the 10-K URL and filing date
        filing_url, filing_date = get_10k_url(cik, filing_year)
        
        if filing_url:
            # Get the 10-K content
            print(f"Downloading filing from: {filing_url}")
            time.sleep(0.1)  # Respect SEC rate limits
            response = requests.get(filing_url, headers=HEADERS)
            
            # Save HTML for debugging
            with open(f"debug/filing_{cik}_{filing_year}.html", "w", encoding="utf-8", errors='ignore') as f:
                f.write(response.text)
            
            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            text = soup.get_text()
            html = str(soup)
            
            # Extract reporting date
            reporting_date = get_reporting_date(text, filing_year)
            
            # Find risk factor section
            risk_section = extract_risk_section(html, soup, cik, filing_year)
            
            # Identify risk factors
            risk_factors = identify_risk_factors(risk_section, cik, filing_year)
            
            if risk_factors:
                for factor in risk_factors:
                    output_rows.append({
                        'cik': cik,
                        'filingyear': filing_year,
                        'filingdate': filing_date or '',
                        'reportingdate': reporting_date or '',
                        'rfdtitle': factor
                    })
                print(f"Added {len(risk_factors)} risk factors")
            else:
                # Add empty row if no risk factors found
                output_rows.append({
                    'cik': cik,
                    'filingyear': filing_year,
                    'filingdate': filing_date or '',
                    'reportingdate': reporting_date or '',
                    'rfdtitle': ''
                })
                print("No risk factors found")
        else:
            # Add empty row if filing not found
            output_rows.append({
                'cik': cik,
                'filingyear': filing_year,
                'filingdate': '',
                'reportingdate': '',
                'rfdtitle': ''
            })
            print("No filing found")
        
        # Sleep to respect SEC rate limits
        time.sleep(1)
    
    # Write output CSV
    output_df = pd.DataFrame(output_rows)
    output_df.to_csv(output_csv, index=False)
    print(f"\nOutput saved to {output_csv}")
    print(f"Debug files saved in 'debug' directory")

if __name__ == "__main__":
    main()