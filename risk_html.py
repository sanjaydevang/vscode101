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
                                print(table_tag)
                                tds = [row.findAll('td') for row in table_tag.findAll('tr')]
                                results = { td[0].string: td[1].string for td in tds }
                                print(results)


                                # for row_tag in table_tag.find_all('tr'):
                                #     print(row_tag)
                                #     if 'Complete submission text file' in row_tag.text:
                                #         print(row_tag)
                                #         for link_tag in row_tag.find_all('a', href=True):
                                #             filing_url = "https://www.sec.gov" + link_tag['href']
                                #             return filing_url, filing_date
        # print(f"10-K URL not found for CIK: {cik}, Year: {filing_year}")
        # return None, None
    except Exception as e:
        # print(f"Error fetching 10-K URL for CIK {cik}: {e}")
        print(e)


def extract_reporting_date(text, filing_year):
    match = re.search(r'for the fiscal year ended ([A-Za-z]+ \d{1,2}, \d{4})', text, re.IGNORECASE)
    if match:
        try:
            return pd.to_datetime(match.group(1)).strftime('%Y-%m-%d')
        except Exception:
            pass
    return f'{filing_year}-12-31'

def find_item_1a_element(soup):
    # Try direct string search first
    item_1a = soup.find(
        string=re.compile(
            r'item\\s*1a\\s*[:\\.\\-–—]?\\s*risk\\s*factors',
            re.IGNORECASE
        )
    )
    if item_1a:
        return item_1a.find_parent()
    # Fallback: search all text nodes
    for tag in soup.find_all(text=True):
        if re.search(r'item\\s*1a\\s*[:\\.\\-–—]?\\s*risk\\s*factors', tag, re.IGNORECASE):
            return BeautifulSoup(str(tag.parent), 'lxml').find()
    return None

def extract_risk_factor_titles_from_html(soup, cik=None, filing_year=None):
    start_elem = find_item_1a_element(soup)
    if not start_elem:
        print(f"Item 1A not found in HTML for CIK {cik}, year {filing_year}!")
        return []
    print(f"Item 1A found for CIK {cik}, year {filing_year}")
    section_elems = []
    current = start_elem
    while current:
        section_elems.append(current)
        next_elem = current.find_next_sibling()
        if next_elem and next_elem.get_text(strip=True):
            if re.search(r'Item\\s*1B\\.?|Item\\s*2\\.?', next_elem.get_text(), re.IGNORECASE):
                break
        current = next_elem
    print("Number of section elements:", len(section_elems))
    titles = []
    for elem in section_elems:
        for tag in elem.find_all(['b', 'strong', 'i']):
            text = tag.get_text(strip=True)
            if 20 <= len(text) <= 250 and text[-1] == '.':
                titles.append(text)
        for p in elem.find_all('p'):
            text = p.get_text(strip=True)
            if (20 <= len(text) <= 250 and text[-1] == '.' and
                not text.lower().startswith('item 1a') and
                not text.lower().startswith('unresolved staff comments') and
                not text.lower().startswith('legal proceedings')):
                titles.append(text)
    print("Titles found:", titles)
    return list(dict.fromkeys(titles))

def main():
    input_csv_path = "rasamplemini_rfdtitle-new.csv"
    output_csv_path = "rasamplemini_rfdtitle_output.csv"
    output_rows = []
    df = pd.read_csv(input_csv_path, dtype={'cik': str})
    df.columns = df.columns.str.lower()
    for index, row in df.iterrows():
        cik = row['cik'].zfill(10)
        filing_year = int(row['filingyear'])
        tenk_url, filing_date = get_10k_url_and_filing_date(cik, filing_year)
        if not tenk_url:
            print(f"Skipping CIK: {cik}, Year: {filing_year} - URL not found")
            continue
        time.sleep(0.1)
        response = requests.get(tenk_url, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'lxml')
        text = soup.get_text()
        reporting_date = extract_reporting_date(text, filing_year)
        risk_factor_titles = extract_risk_factor_titles_from_html(soup, cik, filing_year)
        # for title in risk_factor_titles:
        #     output_rows.append({
        #         'cik': cik,
        #         'filingyear': filing_year,
        #         'filingdate': filing_date,
        #         'reportingdate': reporting_date,
        #         'rfdtitle': title
        #     })
        # time.sleep(1)
        # print(soup.prettify()[:1000])
    # output_df = pd.DataFrame(output_rows)
    # output_df.to_csv(output_csv_path, index=False)
    # print(f"Extraction completed. Output saved to {output_csv_path}")

if __name__ == '__main__':
    main() 