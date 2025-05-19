import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import os
import time
from datetime import datetime
import csv
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SECRiskFactorExtractor:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Risk Factor Research Project user@university.edu'
        }
        self.base_url = "https://www.sec.gov/Archives/"
        self.results = []

    def get_filing_url(self, cik, filing_year):
        """Get the URL for the 10-K filing based on CIK and filing year"""
        # Convert CIK and filing_year to integers
        try:
            cik = int(cik)
            filing_year = int(filing_year)
        except (ValueError, TypeError):
            logger.error(f"Invalid CIK or filing year: {cik}, {filing_year}")
            return None
        
        # Calculate date range for the filing year
        start_date = f"{filing_year}0101"  # January 1st of the year
        end_date = f"{filing_year}1231"    # December 31st of the year
        
        try:
            # Use the EDGAR browse URL to find 10-K filings for the company in the specified year
            search_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K&dateb={end_date}&datea={start_date}&owner=exclude&count=10"
            logger.info(f"Searching for filings with URL: {search_url}")
            
            response = requests.get(search_url, headers=self.headers)
            if response.status_code != 200:
                logger.error(f"Failed to retrieve EDGAR search results for CIK {cik} and year {filing_year}, status code: {response.status_code}")
                return None
            
            # Parse the search results page to find the 10-K filings
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the table with filing results
            filing_table = None
            for table in soup.find_all('table'):
                if 'id' in table.attrs and table['id'] == 'documentsbutton':
                    filing_table = table
                    break
                
                # Sometimes the table might not have an ID
                for row in table.find_all('tr'):
                    if row.find_all('td') and '10-K' in row.text:
                        filing_table = table
                        break
                        
                if filing_table:
                    break
            
            if not filing_table:
                logger.error(f"No 10-K filing found for CIK {cik} in year {filing_year}")
                return None
            
            # Find the first 10-K entry (most recent first)
            filing_url = None
            for row in filing_table.find_all('tr'):
                cols = row.find_all('td')
                if len(cols) >= 2 and '10-K' in cols[0].text:
                    # Find the Documents button
                    doc_button = row.find('a', id=lambda x: x and x.startswith('documentsbutton'))
                    if doc_button:
                        doc_href = doc_button.get('href')
                        if doc_href:
                            filing_url = f"https://www.sec.gov{doc_href}"
                            break
            
            if not filing_url:
                # Alternative way to find the document link
                for link in soup.find_all('a'):
                    href = link.get('href')
                    if href and '/Archives/' in href and '10-K' in link.text:
                        filing_url = f"https://www.sec.gov{href}"
                        break
            
            if not filing_url:
                logger.error(f"Could not find document link for CIK {cik} in year {filing_year}")
                return None
            
            return filing_url
        
        except Exception as e:
            logger.error(f"Error getting filing URL for CIK {cik}: {str(e)}")
            return None

    def get_edgar_documents(self, url):
        """Get the individual document URLs from the filing index page"""
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code != 200:
                logger.error(f"Failed to retrieve index page: {url}, status code: {response.status_code}")
                return None

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find the table with class 'tableFile' (this is the document table)
            doc_table = soup.find('table', class_='tableFile')
            if not doc_table:
                logger.error(f"Could not find document table in {url}")
                return None

            # Try to find the first HTML document with type '10-K' or '10-K/A'
            for row in doc_table.find_all('tr')[1:]:
                cells = row.find_all('td')
                if len(cells) >= 4:
                    doc_type = cells[3].text.strip()
                    doc_link = cells[2].find('a', href=True)
                    if doc_type in ['10-K', '10-K/A'] and doc_link:
                        href = doc_link['href']
                        if href.endswith('.htm') or href.endswith('.html'):
                            filing_doc_url = f"https://www.sec.gov{href}"
                            logger.info(f"Found 10-K document URL: {filing_doc_url}")
                            return filing_doc_url

            # Fallback: return the first HTML document in the table
            for row in doc_table.find_all('tr')[1:]:
                cells = row.find_all('td')
                if len(cells) >= 3:
                    doc_link = cells[2].find('a', href=True)
                    if doc_link:
                        href = doc_link['href']
                        if href.endswith('.htm') or href.endswith('.html'):
                            filing_doc_url = f"https://www.sec.gov{href}"
                            logger.info(f"Found HTML document URL (fallback): {filing_doc_url}")
                            return filing_doc_url

            logger.error(f"Could not find 10-K document URL in {url}")
            return None

        except Exception as e:
            logger.error(f"Error getting documents from {url}: {str(e)}")
            return None

    def extract_filing_date(self, soup, text):
        # Try to find in HTML
        possible_labels = ['Filing Date', 'FILED', 'Date of Report']
        for label in possible_labels:
            label_elem = soup.find(string=re.compile(label, re.IGNORECASE))
            if label_elem:
                # Look for a date in the same or nearby element
                date_match = re.search(r'(\d{2}/\d{2}/\d{4})|([A-Za-z]+ \d{1,2}, \d{4})', label_elem)
                if date_match:
                    date_str = date_match.group(0)
                    for fmt in ("%B %d, %Y", "%m/%d/%Y"):
                        try:
                            return pd.to_datetime(date_str).strftime('%Y-%m-%d')
                        except Exception:
                            continue
        # Fallback: try in text
        patterns = [
            r'filed as of ([A-Za-z]+ \d{1,2}, \d{4})',
            r'filed as of (\d{2}/\d{2}/\d{4})',
            r'filed on ([A-Za-z]+ \d{1,2}, \d{4})',
            r'filed on (\d{2}/\d{2}/\d{4})'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                for fmt in ("%B %d, %Y", "%m/%d/%Y"):
                    try:
                        return pd.to_datetime(date_str).strftime('%Y-%m-%d')
                    except Exception:
                        continue
        return None

    def extract_reporting_date(self, text, filing_year):
        match = re.search(r'for the fiscal year ended ([A-Za-z]+ \d{1,2}, \d{4})', text, re.IGNORECASE)
        if match:
            try:
                return pd.to_datetime(match.group(1)).strftime('%Y-%m-%d')
            except Exception:
                pass
        return f'{filing_year}-12-31'

    def extract_risk_factor_section(self, url, filing_year):
        """Extract the Item 1A Risk Factors section from the 10-K document"""
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code != 200:
                logger.error(f"Failed to retrieve document: {url}, status code: {response.status_code}")
                return None, None, None
                
            html_content = response.text
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract filing date and reporting date
            filing_date = self.extract_filing_date(soup, html_content)
            reporting_date = self.extract_reporting_date(html_content, filing_year)
            
            # Extract text content
            text_content = soup.get_text(" ", strip=True)
            
            # Debug: Print first 500 characters of text content
            logger.info(f"First 500 characters of text content: {text_content[:500]}")
            
            # Find Item 1A section with more flexible patterns
            item_1a_patterns = [
                r'(?:Item|ITEM)\s*1A\.?\s*(?:Risk\s*Factors|RISK\s*FACTORS)',
                r'(?:Item|ITEM)\s*1A\.?\s*(?:Risk\s*Factors|RISK\s*FACTORS)\.?',
                r'(?:Item|ITEM)\s*1A\.?\s*(?:Risk\s*Factors|RISK\s*FACTORS)\.?\s*(?:Item|ITEM)\s*1A\.?\s*(?:Risk\s*Factors|RISK\s*FACTORS)',
                r'(?:Item|ITEM)\s*1A\.?\s*(?:Risk\s*Factors|RISK\s*FACTORS)\.?\s*(?:Item|ITEM)\s*1A\.?\s*(?:Risk\s*Factors|RISK\s*FACTORS)\.?'
            ]
            
            start_match = None
            for pattern in item_1a_patterns:
                start_match = re.search(pattern, text_content, re.IGNORECASE)
                if start_match:
                    logger.info(f"Found Item 1A with pattern: {pattern}")
                    break
            
            if not start_match:
                logger.error(f"Could not find Item 1A Risk Factors section in {url}")
                return None, filing_date, reporting_date
                
            start_pos = start_match.end()
            
            # Find the end of Item 1A (either Item 1B or Item 2)
            item_1b_pattern = re.compile(r'(?:Item|ITEM)\s*1B\.?', re.IGNORECASE)
            item_2_pattern = re.compile(r'(?:Item|ITEM)\s*2\.?', re.IGNORECASE)
            
            end_match_1b = item_1b_pattern.search(text_content[start_pos:])
            end_match_2 = item_2_pattern.search(text_content[start_pos:])
            
            if end_match_1b:
                end_pos = start_pos + end_match_1b.start()
                logger.info("Found end of section at Item 1B")
            elif end_match_2:
                end_pos = start_pos + end_match_2.start()
                logger.info("Found end of section at Item 2")
            else:
                # Default to a reasonable amount of text if no clear ending is found
                end_pos = start_pos + 50000  # Arbitrary limit
                logger.info("No clear end found, using default limit")
            
            # Extract the risk factors section
            risk_factors_section = text_content[start_pos:end_pos]
            
            # Debug: Print first 500 characters of risk factors section
            logger.info(f"First 500 characters of risk factors section: {risk_factors_section[:500]}")
            
            return risk_factors_section, filing_date, reporting_date
        
        except Exception as e:
            logger.error(f"Error extracting risk factor section from {url}: {str(e)}")
            return None, None, None

    def extract_risk_factor_titles(self, risk_factors_section):
        """Extract the risk factor titles from the risk factors section"""
        try:
            if not risk_factors_section:
                return []
                
            # Debug: Print the first 1000 characters of the risk factors section
            logger.info(f"First 1000 characters of risk factors section: {risk_factors_section[:1000]}")
            
            # Various patterns to identify risk factor titles
            patterns = [
                # Pattern 1: Numbered risk factors (e.g., "1. Risk of X")
                r'(?:\n|\r\n)(?:\d+\.|\•|\*)\s*([A-Z][^.]*?\.)',
                
                # Pattern 2: All caps titles
                r'(?:\n|\r\n)([A-Z][A-Z0-9\s,\.&;:\-\'\"()]+\.)',
                
                # Pattern 3: Sentences starting with capital letters
                r'(?:\n|\r\n)([A-Z][^.]*?\.)',
                
                # Pattern 4: Bold or italic text (if HTML tags remain)
                r'(?:<b>|<strong>|<i>|<em>)(.*?)(?:</b>|</strong>|</i>|</em>)',
                
                # Pattern 5: Risk factor specific patterns
                r'(?:Risk|RISK)\s*(?:Factor|FACTOR)[s:]?\s*([A-Z][^.]*?\.)',
                r'(?:We|WE)\s*(?:face|FACE|may|MAY|could|COULD)\s*(?:risks|RISKS)\s*(?:related|RELATED)\s*(?:to|TO)\s*([A-Z][^.]*?\.)'
            ]
            
            titles = []
            for pattern in patterns:
                matches = re.findall(pattern, risk_factors_section)
                if matches:
                    logger.info(f"Found {len(matches)} titles with pattern: {pattern}")
                titles.extend(matches)
            
            # Clean up titles
            cleaned_titles = []
            for title in titles:
                # Remove common prefixes
                title = re.sub(r'^(?:Risk Factor|RISK FACTOR)[s:]?\s*', '', title)
                title = re.sub(r'^(?:We|WE)\s*(?:face|FACE|may|MAY|could|COULD)\s*(?:risks|RISKS)\s*(?:related|RELATED)\s*(?:to|TO)\s*', '', title)
                
                # Remove extra whitespace and normalize
                title = re.sub(r'\s+', ' ', title).strip()
                
                # Only keep substantive titles (longer than 10 characters)
                if len(title) > 10:
                    cleaned_titles.append(title)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_titles = []
            for title in cleaned_titles:
                if title not in seen:
                    seen.add(title)
                    unique_titles.append(title)
            
            # Additional filtering to remove false positives
            filtered_titles = []
            for title in unique_titles:
                # Skip titles that are too generic
                if title.lower() in ['risk factors', 'overview', 'introduction', 'summary', 'table of contents']:
                    continue
                    
                # Skip titles that are just dates or numbers
                if re.match(r'^(?:\d+|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})$', title):
                    continue
                    
                filtered_titles.append(title)
            
            logger.info(f"Found {len(filtered_titles)} unique risk factor titles")
            if filtered_titles:
                logger.info(f"Sample titles: {filtered_titles[:3]}")
            
            return filtered_titles
        
        except Exception as e:
            logger.error(f"Error extracting risk factor titles: {str(e)}")
            return []

    def process_filing(self, cik, filing_year):
        """Process a single filing to extract risk factor titles"""
        try:
            # Get the filing index URL
            filing_url = self.get_filing_url(cik, filing_year)
            if not filing_url:
                logger.warning(f"Could not find filing URL for CIK {cik} in year {filing_year}")
                return []
                
            # Get the actual 10-K document URL
            document_url = self.get_edgar_documents(filing_url)
            if not document_url:
                logger.warning(f"Could not find 10-K document URL for CIK {cik} in year {filing_year}")
                return []
                
            # Extract the risk factors section and dates
            risk_factors_section, filing_date, reporting_date = self.extract_risk_factor_section(document_url, filing_year)
            if not risk_factors_section:
                logger.warning(f"Could not extract risk factors section for CIK {cik} in year {filing_year}")
                return []
                
            # Extract risk factor titles
            risk_factor_titles = self.extract_risk_factor_titles(risk_factors_section)
            
            # Create result entries
            result_entries = []
            for title in risk_factor_titles:
                result_entries.append({
                    'cik': int(cik),
                    'filingyear': int(filing_year),
                    'filingdate': filing_date,
                    'reportingdate': reporting_date,
                    'rfdtitle': title
                })
                
            return result_entries
        
        except Exception as e:
            logger.error(f"Error processing filing for CIK {cik} in year {filing_year}: {str(e)}")
            return []

    def process_all_filings(self, input_file, output_file):
        """Process all filings from the input file and save results to the output file"""
        try:
            # Read input data
            if input_file.endswith('.csv'):
                input_data = pd.read_csv(input_file)
            elif input_file.endswith('.xlsx'):
                input_data = pd.read_excel(input_file)
            else:
                logger.error(f"Unsupported input file format: {input_file}")
                return
            
            # Convert CIK and filing year columns to integers
            if 'cik' in input_data.columns:
                input_data['cik'] = input_data['cik'].astype(int)
            if 'filingyear' in input_data.columns:
                input_data['filingyear'] = input_data['filingyear'].astype(int)
                
            start_time = time.time()
            total_results = []
            
            # Process each CIK and filing year
            for index, row in input_data.iterrows():
                cik = int(row['cik'])
                filing_year = int(row['filingyear'])
                
                logger.info(f"Processing CIK {cik} for year {filing_year}")
                
                # Process the filing
                results = self.process_filing(cik, filing_year)
                
                # Add to total results
                total_results.extend(results)
                
                # Respect SEC's rate limit (max 10 requests per second)
                time.sleep(0.1)
                
            # Save results to output file
            results_df = pd.DataFrame(total_results)
            
            if output_file.endswith('.csv'):
                results_df.to_csv(output_file, index=False)
            elif output_file.endswith('.xlsx'):
                results_df.to_excel(output_file, index=False)
            else:
                results_df.to_csv(output_file + '.csv', index=False)
                
            elapsed_time = time.time() - start_time
            logger.info(f"Processed {len(input_data)} filings in {elapsed_time:.2f} seconds")
            logger.info(f"Found {len(total_results)} risk factor titles")
            logger.info(f"Results saved to {output_file}")
            
            return results_df
        
        except Exception as e:
            logger.error(f"Error processing all filings: {str(e)}")
            return None

def create_sample_input_file(output_file, ciks, years):
    """Create a sample input file with the given CIKs and years"""
    try:
        data = []
        for cik in ciks:
            # Convert CIK to integer if it's not already
            try:
                cik = int(cik)
            except (ValueError, TypeError):
                logger.error(f"Invalid CIK: {cik}")
                continue
                
            for year in years:
                # Convert year to integer if it's not already
                try:
                    year = int(year)
                except (ValueError, TypeError):
                    logger.error(f"Invalid year: {year}")
                    continue
                    
                data.append({
                    'cik': cik,
                    'filingyear': year,
                    'filingdate': '',
                    'reportingdate': '',
                    'rfdtitle': ''
                })
                
        df = pd.DataFrame(data)
        
        if output_file.endswith('.csv'):
            df.to_csv(output_file, index=False)
        elif output_file.endswith('.xlsx'):
            df.to_excel(output_file, index=False)
        else:
            df.to_csv(output_file + '.csv', index=False)
            
        logger.info(f"Created sample input file {output_file} with {len(data)} entries")
        
    except Exception as e:
        logger.error(f"Error creating sample input file: {str(e)}")

def main():
    # Get user input for which action to perform
    print("SEC Risk Factor Title Extractor")
    print("1. Create sample input file")
    print("2. Process existing input file")
    choice = input("Enter your choice (1 or 2): ")
    
    if choice == '1':
        # Get CIKs from user
        ciks_input = input("Enter CIKs (comma separated): ")
        ciks = [cik.strip() for cik in ciks_input.split(',')]
        
        # Get years from user
        years_input = input("Enter years (comma separated, e.g. 2018,2019,2020): ")
        years = [int(year.strip()) for year in years_input.split(',')]
        
        # Get output file name
        output_file = input("Enter output file name (e.g. sample_input.csv): ")
        
        # Create sample input file
        create_sample_input_file(output_file, ciks, years)
        
    elif choice == '2':
        # Get input file name
        input_file = input("Enter input file name (e.g. rasamplemini_rfdtitle.csv): ")
        
        # Get output file name
        output_file = input("Enter output file name (e.g. rasamplemini_rfdtitle_output.csv): ")
        
        # Process input file
        extractor = SECRiskFactorExtractor()
        results = extractor.process_all_filings(input_file, output_file)
        
    else:
        print("Invalid choice. Please enter 1 or 2.")

if __name__ == "__main__":
    main()