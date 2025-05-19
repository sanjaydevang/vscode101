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
                                        filing_url = "https://www.sec.gov" + link_tag['href']
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
    return f'{filing_year}-12-31'


def find_risk_factor_text(soup):
    start_pattern = re.compile(r"item[\s\t]*1a[\s\t]*[\.:]?\s*risk\s*factors", re.IGNORECASE)
    end_pattern = re.compile(r"item[\s\t]*1b[\s\t]*[\.:]?\s*unresolved\s*staff\s*comments", re.IGNORECASE)

    start_tag = None
    end_tag = None

    # Step 1: Identify the tag where 'ITEM 1A. RISK FACTORS' starts

    # === 1. Match plain text in document ===
    for el in soup.find_all(string=start_pattern):
        clean_text = re.sub(r'[\n\r\t\'"]+', ' ', el).strip()
        start_tag = el.parent.parent.parent

    # === 2. Match table-based split cells ===
    for table in soup.find_all("table"):
        cells = table.find_all("td")
        if len(cells) >= 2:
            left = cells[0].get_text(strip=True)
            right = cells[1].get_text(strip=True)
            combined = f"{left} {right}"
            normalized = re.sub(r'\s+', ' ', combined.lower())
            if start_pattern.search(normalized):
                start_tag = cells
                # results.append(combined.strip())

        # === 1. Match plain text in document ===
    for el in soup.find_all(string=end_pattern):
        clean_text = re.sub(r'[\n\r\t\'"]+', ' ', el).strip()
        end_tag = el.parent.parent.parent
        # results.append(clean_text)

        # === 2. Match table-based split cells ===
    for table in soup.find_all("table"):
        cells = table.find_all("td")
        if len(cells) >= 2:
            left = cells[0].get_text(strip=True)
            right = cells[1].get_text(strip=True)
            combined = f"{left} {right}"
            normalized = re.sub(r'\s+', ' ', combined.lower())
            if end_pattern.search(normalized):
                end_tag = cells
                # results.append(combined.strip())
    # for tag in soup.find_all():
    #     # 1. Check text content
    #     # print(tag)
    #     if start_pattern.search(tag.get_text(strip=True)):
    #         print("here", tag)
    #         start_tag = tag
    #         break
    #     # 2. Check table-based split headers
    #     if tag.name == "table":
    #         tds = tag.find_all("td")
    #         if len(tds) >= 2:
    #             combined = f"{tds[0].get_text(strip=True)} {tds[1].get_text(strip=True)}"
    #             if start_pattern.search(re.sub(r'\s+', ' ', combined.lower())):
    #                 start_tag = tag
    #                 break
    #
    # # Step 2: Identify the tag where 'ITEM 1B. UNRESOLVED STAFF COMMENTS' starts
    # for tag in soup.find_all(True):
    #     if tag.string and end_pattern.search(tag.string.strip()):
    #         end_tag = tag
    #         break
    #     if tag.name == "table":
    #         tds = tag.find_all("td")
    #         if len(tds) >= 2:
    #             combined = f"{tds[0].get_text(strip=True)} {tds[1].get_text(strip=True)}"
    #             if end_pattern.search(re.sub(r'\s+', ' ', combined.lower())):
    #                 end_tag = tag
    #                 break

    print(f"Start tag: {start_tag}")
    print(f"End tag: {end_tag}")

    content_tags = []
    risks = []

    if start_tag and end_tag:
        current = start_tag.find_next_sibling()
        while current and current != end_tag:
            content_tags.append(current)
            current = current.find_next_sibling()

        for tag in content_tags:
            if tag.find(['b', 'strong', 'i', 'em', 'u']):
                risks.append(tag.get_text())
    else:
        print("Start or end tag not found.")
    return risks


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
        print(tenk_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'lxml')
        text = soup.get_text()
        reporting_date = extract_reporting_date(text, filing_year)
        risk_factor_titles = find_risk_factor_text(soup)

        for title in risk_factor_titles:
            cleaned = re.sub(r'[\n\r\t\"\\]+', ' ', title).strip()
            output_rows.append({
                'cik': row['cik'],
                'filingyear': filing_year,
                'filingdate': filing_date,
                'reportingdate': reporting_date,
                'rfdtitle': cleaned
            })
        time.sleep(1)
    output_df = pd.DataFrame(output_rows)
    output_df.to_csv(output_csv_path, index=False)
    print(f"Extraction completed. Output saved to {output_csv_path}")


if __name__ == '__main__':
    main()
