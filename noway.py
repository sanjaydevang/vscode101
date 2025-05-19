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
        # Pad CIK with leading zeros to 10 digits
        cik_padded = str(cik).zfill(10)
        
        # Get the list of filings for the specified year
        try:
            index_url = f"https://www.sec.gov/Archives/edgar/full-index/{filing_year}/QTR1/master.idx"
            response = requests.get(index_url, headers=self.headers)
            if response.status_code != 200:
                index_url = f"https://www.sec.gov/Archives/edgar/full-index/{filing_year}/QTR2/master.idx"
                response = requests.get(index_url, headers=self.headers)
            if response.status_code != 200:
                index_url = f"https://www.sec.gov/Archives/edgar/full-index/{filing_year}/QTR3/master.idx"
                response = requests.get(index_url, headers=self.headers)
            if response.status_code != 200:
                index_url = f"https://www.sec.gov/Archives/edgar/full-index/{filing_year}/QTR4/master.idx"
                response = requests.get(index_url, headers=self.headers)
                
            if response.status_code != 200:
                logger.error(f"Failed to retrieve master index for CIK {cik} and year {filing_year}")
                return None
                
            content = response.text
            
            # Find the 10-K filing for the specific CIK
            pattern = re.compile(f"{cik_padded}.*?10-K.*?edgar/data.*?\\.txt", re.DOTALL)
            matches = pattern.findall(content)
            
            if not matches:
                # Try the other quarters
                for qtr in [2, 3, 4]:
                    index_url = f"https://www.sec.gov/Archives/edgar/full-index/{filing_year}/QTR{qtr}/master.idx"
                    response = requests.get(index_url, headers=self.headers)
                    if response.status_code == 200:
                        content = response.text
                        matches = pattern.findall(content)
                        if matches:
                            break
            
            if not matches:
                logger.error(f"No 10-K filing found for CIK {cik} in year {filing_year}")
                return None
                
            # Get the URL for the first match (most recent 10-K for the year)
            file_info = matches[0].split()
            file_path = file_info[-1]
            
            # Return the URL to the HTML version of the filing
            url = self.base_url + file_path
            
            # Instead of using the .txt file directly, convert to the HTML version
            # by replacing the .txt with the directory and index.htm
            html_url = url.replace('.txt', '/' + file_path.split('/')[-1].replace('.txt', '-index.html'))
            
            return html_url
        
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
            
            # Find the main 10-K document (usually the first one)
            documents = []
            for table in soup.find_all('table'):
                for row in table.find_all('tr'):
                    cells = row.find_all('td')
                    if len(cells) >= 3:
                        doc_type = cells[0].text.strip()
                        if '10-K' in doc_type:
                            doc_href = cells[2].find('a').get('href') if cells[2].find('a') else None
                            if doc_href:
                                doc_url = f"https://www.sec.gov{doc_href}"
                                documents.append(doc_url)
                                break
            
            # If no 10-K document found, try another approach
            if not documents:
                for link in soup.find_all('a'):
                    href = link.get('href')
                    if href and '10k.htm' in href.lower() or '10-k.htm' in href.lower():
                        doc_url = f"https://www.sec.gov{href}"
                        documents.append(doc_url)
                        break
            
            return documents[0] if documents else None
        
        except Exception as e:
            logger.error(f"Error getting documents from {url}: {str(e)}")
            return None

    def extract_filing_date(self, text):
        """Extract the filing date from the 10-K document"""
        try:
            # Look for common filing date patterns
            patterns = [
                r'FILED\s*:\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})',
                r'Filed\s*(?:as of|on)\s*(?:the)?\s*(?:date)?\s*(?:hereof)?\s*:\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})',
                r'Date\s*of\s*report.*?(\d{2}/\d{2}/\d{4})',
                r'DATE\s*OF\s*REPORT.*?(\d{2}/\d{2}/\d{4})',
                r'filing\s*date.*?(\d{2}/\d{2}/\d{4})',
                r'FILING\s*DATE.*?(\d{2}/\d{2}/\d{4})',
                r'As\s*filed\s*with.*?on\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})'
            ]
            
            for pattern in patterns:
                matches = re.search(pattern, text, re.IGNORECASE)
                if matches:
                    date_str = matches.group(1)
                    try:
                        # Parse date in various formats
                        if '/' in date_str:
                            date_obj = datetime.strptime(date_str, '%m/%d/%Y')
                        else:
                            date_obj = datetime.strptime(date_str, '%B %d, %Y')
                        return date_obj.strftime('%Y-%m-%d')
                    except ValueError:
                        continue
            
            return None
        except Exception as e:
            logger.error(f"Error extracting filing date: {str(e)}")
            return None

    def extract_reporting_date(self, text):
        """Extract the fiscal year end date (reporting date) from the 10-K document"""
        try:
            # Look for common reporting date patterns
            patterns = [
                r'(?:fiscal|FISCAL)?\s*(?:year|YEAR)\s*(?:ended|ENDED)\s*(?:on)?\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})',
                r'(?:fiscal|FISCAL)?\s*(?:year|YEAR)\s*(?:ended|ENDED)\s*(?:on)?\s*(\d{2}/\d{2}/\d{4})',
                r'(?:for the|FOR THE)\s*(?:fiscal|FISCAL)?\s*(?:year|YEAR)\s*(?:ended|ENDED)\s*(?:on)?\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})',
                r'(?:for the|FOR THE)\s*(?:fiscal|FISCAL)?\s*(?:year|YEAR)\s*(?:ended|ENDED)\s*(?:on)?\s*(\d{2}/\d{2}/\d{4})',
                r'(?:fiscal|FISCAL)?\s*(?:year|YEAR)\s*(?:end|END)(?:ed|ED)?\s*(?:on)?\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})',
                r'(?:fiscal|FISCAL)?\s*(?:year|YEAR)\s*(?:end|END)(?:ed|ED)?\s*(?:on)?\s*(\d{2}/\d{2}/\d{4})'
            ]
            
            for pattern in patterns:
                matches = re.search(pattern, text, re.IGNORECASE)
                if matches:
                    date_str = matches.group(1)
                    try:
                        # Parse date in various formats
                        if '/' in date_str:
                            date_obj = datetime.strptime(date_str, '%m/%d/%Y')
                        else:
                            date_obj = datetime.strptime(date_str, '%B %d, %Y')
                        return date_obj.strftime('%Y-%m-%d')
                    except ValueError:
                        continue
            
            # If no match found, check for common fiscal year end dates like December 31
            for month in ['December', 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November']:
                for day in ['31', '30', '29', '28', '27']:
                    pattern = f"{month}\\s+{day}"
                    if re.search(pattern, text, re.IGNORECASE):
                        filing_year_match = re.search(r'\d{4}', text)
                        if filing_year_match:
                            year = filing_year_match.group(0)
                            try:
                                date_obj = datetime.strptime(f"{month} {day}, {year}", '%B %d, %Y')
                                return date_obj.strftime('%Y-%m-%d')
                            except ValueError:
                                continue
            
            return None
        except Exception as e:
            logger.error(f"Error extracting reporting date: {str(e)}")
            return None

    def extract_risk_factor_section(self, url):
        """Extract the Item 1A Risk Factors section from the 10-K document"""
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code != 200:
                logger.error(f"Failed to retrieve document: {url}, status code: {response.status_code}")
                return None, None, None
                
            html_content = response.text
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract filing date and reporting date
            filing_date = self.extract_filing_date(html_content)
            reporting_date = self.extract_reporting_date(html_content)
            
            # Extract text content
            text_content = soup.get_text(" ", strip=True)
            
            # Find Item 1A section
            item_1a_pattern = re.compile(r'(?:Item|ITEM)\s*1A\.?\s*(?:Risk\s*Factors|RISK\s*FACTORS)', re.IGNORECASE)
            item_1b_pattern = re.compile(r'(?:Item|ITEM)\s*1B\.?', re.IGNORECASE)
            item_2_pattern = re.compile(r'(?:Item|ITEM)\s*2\.?', re.IGNORECASE)
            
            # Search for Item 1A in the HTML content
            start_match = item_1a_pattern.search(text_content)
            if not start_match:
                logger.error(f"Could not find Item 1A Risk Factors section in {url}")
                return None, filing_date, reporting_date
                
            start_pos = start_match.end()
            
            # Find the end of Item 1A (either Item 1B or Item 2)
            end_match_1b = item_1b_pattern.search(text_content[start_pos:])
            end_match_2 = item_2_pattern.search(text_content[start_pos:])
            
            if end_match_1b:
                end_pos = start_pos + end_match_1b.start()
            elif end_match_2:
                end_pos = start_pos + end_match_2.start()
            else:
                # Default to a reasonable amount of text if no clear ending is found
                end_pos = start_pos + 50000  # Arbitrary limit
            
            # Extract the risk factors section
            risk_factors_section = text_content[start_pos:end_pos]
            
            return risk_factors_section, filing_date, reporting_date
        
        except Exception as e:
            logger.error(f"Error extracting risk factor section from {url}: {str(e)}")
            return None, None, None

    def extract_risk_factor_titles(self, risk_factors_section):
        """Extract the risk factor titles from the risk factors section"""
        try:
            if not risk_factors_section:
                return []
                
            # Various patterns to identify risk factor titles
            # These titles are typically formatted in bold or with special formatting
            # and often followed by a paragraph of explanatory text
            
            # Pattern 1: Sentences ending with a period followed by a paragraph break
            pattern1 = r'([A-Z][^.]*?\.)\s*(?:\n\n|\r\n\r\n)'
            
            # Pattern 2: Bold or italic text (indicated by HTML tags that might remain)
            pattern2 = r'(?:<b>|<strong>|<i>|<em>)(.*?)(?:</b>|</strong>|</i>|</em>)'
            
            # Pattern 3: Lines in all caps or starting with capitals and ending with period
            pattern3 = r'\n([A-Z][A-Z0-9\s,\.&;:\-\'\"()]+\.)'
            
            # Pattern 4: Numbered risk factors
            pattern4 = r'(?:\n|\r\n)(?:\d+\.|\•|\*)\s*([A-Z][^.]*?\.)'
            
            # Combine all patterns
            all_patterns = [pattern1, pattern2, pattern3, pattern4]
            
            titles = []
            for pattern in all_patterns:
                matches = re.findall(pattern, risk_factors_section)
                titles.extend(matches)
            
            # Clean up titles
            cleaned_titles = []
            for title in titles:
                # Remove common prefixes
                title = re.sub(r'^(?:Risk Factor|RISK FACTOR)[s:]?\s*', '', title)
                
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
                
            # If we didn't find any titles with the above patterns, try a more aggressive approach
            if not filtered_titles:
                # Look for sentences that start with capital letters and end with periods
                sentences = re.findall(r'([A-Z][^.]*?\.)', risk_factors_section)
                for sentence in sentences:
                    # Only consider sentences that seem like titles (not too long, not too short)
                    if 10 < len(sentence) < 200:
                        filtered_titles.append(sentence.strip())
            
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
            risk_factors_section, filing_date, reporting_date = self.extract_risk_factor_section(document_url)
            if not risk_factors_section:
                logger.warning(f"Could not extract risk factors section for CIK {cik} in year {filing_year}")
                return []
                
            # Extract risk factor titles
            risk_factor_titles = self.extract_risk_factor_titles(risk_factors_section)
            
            # Create result entries
            result_entries = []
            for title in risk_factor_titles:
                result_entries.append({
                    'cik': cik,
                    'filingyear': filing_year,
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
                
            start_time = time.time()
            total_results = []
            
            # Process each CIK and filing year
            for index, row in input_data.iterrows():
                cik = row['cik']
                filing_year = row['filingyear']
                
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
            for year in years:
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