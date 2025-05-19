import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
import os

# Replace with your email
HEADERS = {
    'User-Agent': 's.devang@gwu.edu', 
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'www.sec.gov'
}


if not os.path.exists('debug'):
    os.makedirs('debug')

def get_10k_url(cik, filing_year):
    cik_str = str(cik).zfill(10)
    filing_year = int(filing_year)

    start_date = f"{filing_year-1}1201"
    end_date = f"{filing_year}1231"

    url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik_str}&type=10-K&dateb={end_date}&datea={start_date}&owner=exclude&count=40"
    print(f"Searching: {url}")

    try:
        time.sleep(0.1)
        response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            print(f"Error: Status code {response.status_code} for {url}")
            return None, None

        with open(f"debug/search_{cik}_{filing_year}.html", "w", encoding="utf-8", errors='ignore') as f:
            f.write(response.text)

        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table', class_='tableFile2')

        if not table:
            print(f"No filing table found for CIK: {cik}, Year: {filing_year}")
            return None, None

        for row in table.find_all('tr')[1:]:
            cells = row.find_all('td')
            if len(cells) >= 4:
                filing_type = cells[0].text.strip()
                filing_date = cells[3].text.strip()

                if filing_type == "10-K" and str(filing_year) in filing_date:
                    filing_link = cells[1].find('a', href=True)
                    if filing_link:
                        detail_url = "https://www.sec.gov" + filing_link['href']
                        print(f"Found filing page: {detail_url}")

                        try:
                            date_obj = pd.to_datetime(filing_date)
                            filing_date = date_obj.strftime('%m/%d/%Y')
                        except:
                            pass

                        time.sleep(0.1)
                        detail_response = requests.get(detail_url, headers=HEADERS)
                        detail_soup = BeautifulSoup(detail_response.content, 'html.parser')

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
    start_pos = None
    for pattern in start_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            start_pos = match.end()
            break

    if start_pos is None:
        return None

    end_pos = None
    for pattern in end_patterns:
        match = re.search(pattern, html[start_pos:], re.IGNORECASE)
        if match:
            end_pos = start_pos + match.start()
            break

    if end_pos is None:
        end_pos = start_pos + 100000

    section_html = html[start_pos:end_pos]
    with open(f"debug/risk_section_{cik}_{filing_year}.html", "w", encoding="utf-8", errors='ignore') as f:
        f.write(section_html)

    return BeautifulSoup(section_html, 'html.parser')

def identify_risk_factors(section_soup, cik, filing_year):
    if section_soup is None:
        return []

    section_text = section_soup.get_text()
    with open(f"debug/risk_section_text_{cik}_{filing_year}.txt", "w", encoding="utf-8", errors='ignore') as f:
        f.write(section_text)

    risk_factors = []
    bold_titles = []
    for tag in section_soup.find_all(['b', 'strong']):
        text = tag.get_text(strip=True)
        if text and len(text) > 15 and not text.upper().startswith("ITEM"):
            parent = tag.find_parent('p')
            if parent:
                full_text = parent.get_text(strip=True)
                if full_text.startswith(text):
                    match = re.search(r'^(.*?\.)', full_text)
                    if match:
                        title = match.group(1).strip()
                        if is_valid_risk_factor(title):
                            bold_titles.append(title)
                else:
                    if is_valid_risk_factor(text):
                        bold_titles.append(text)
            else:
                if is_valid_risk_factor(text):
                    bold_titles.append(text)

    if cik == '4962':  # American Express
        sentences = re.findall(r'([A-Z][^\.]+\.)(?:\s+[A-Z])', section_text)
        for sentence in sentences:
            sentence = sentence.strip()
            if is_valid_risk_factor(sentence) and len(sentence.split()) >= 7:
                if sentence not in bold_titles:
                    bold_titles.append(sentence)

    if bold_titles:
        risk_factors.extend(bold_titles)
    else:
        paragraphs = section_soup.find_all('p')
        for p in paragraphs:
            text = p.get_text(strip=True)
            if is_paragraph_risk_factor(text):
                match = re.search(r'^(.*?\.)', text)
                if match:
                    title = match.group(1).strip()
                    if is_valid_risk_factor(title) and len(title.split()) >= 5:
                        risk_factors.append(title)

    if len(risk_factors) < 5:
        risk_phrases = find_risk_phrases(section_text)
        for phrase in risk_phrases:
            if phrase not in risk_factors and is_valid_risk_factor(phrase) and len(phrase.split()) >= 5:
                risk_factors.append(phrase)

    clean_factors = []
    seen = set()
    for factor in risk_factors:
        cleaned = re.sub(r'\s+', ' ', factor).strip()
        if (cleaned and cleaned not in seen and
            not cleaned.upper().startswith("ITEM") and
            len(cleaned.split()) >= 5):
            clean_factors.append(cleaned)
            seen.add(cleaned)

    return clean_factors

def is_valid_risk_factor(text):
    risk_words = ['risk', 'risks', 'adverse', 'impact', 'affect', 'failure', 'unable',
                 'not', 'negative', 'loss', 'damage', 'subject to', 'litigation',
                 'could', 'may', 'might', 'regulatory', 'decline', 'decrease',
                 'competition', 'competitive', 'challenges', 'difficult', 'uncertain',
                 'volatility', 'fluctuation']
    text_lower = text.lower()
    has_risk_word = any(word in text_lower for word in risk_words)
    ends_properly = text.strip().endswith('.')
    good_length = 10 < len(text.split()) < 50
    return has_risk_word and ends_properly and good_length

def is_paragraph_risk_factor(text):
    starter_phrases = ['we face', 'we are subject', 'our business', 'our success',
                      'we may', 'we cannot', 'we depend', 'we have', 'if we',
                      'the company', 'changes in', 'failure to']
    text_lower = text.lower()
    starts_with_phrase = any(text_lower.startswith(phrase) for phrase in starter_phrases)
    risk_words = ['risk', 'risks', 'adverse', 'impact', 'affect', 'failure', 'unable',
                 'not', 'negative', 'loss', 'damage', 'subject to', 'litigation',
                 'could', 'may', 'might', 'regulatory']
    has_risk_word = any(word in text_lower for word in risk_words)
    good_length = 20 < len(text) < 1000
    return (starts_with_phrase or has_risk_word) and good_length

def find_risk_phrases(text):
    risk_phrases = []
    for starter in ['We face', 'We are subject', 'Our business', 'Our ability',
                   'We may', 'We cannot', 'We depend', 'Our success', 'If we',
                   'The Company', 'Changes in', 'Failure to']:
        pattern = f'{re.escape(starter)}[^\.]+\.'
        matches = re.findall(pattern, text, re.IGNORECASE)
        risk_phrases.extend(matches)

    for risk_word in ['significant risk', 'material adverse', 'substantial risk',
                     'negatively impact', 'adversely affect', 'substantial harm',
                     'serious consequences', 'adverse effect', 'significant negative']:
        pattern = f'[A-Z][^\.]*{re.escape(risk_word)}[^\.]+\.'
        matches = re.findall(pattern, text, re.IGNORECASE)
        risk_phrases.extend(matches)

    return risk_phrases

def get_reporting_date(text, filing_year):
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

    return f'12/31/{int(filing_year)-1}'

def main():
    input_csv = "rasamplemini_rfdtitle_input.csv"
    output_csv = "rasamplemini_rfdtitle_output.csv"

    df = pd.read_csv(input_csv, dtype={'cik': str, 'filingyear': str})
    output_rows = []

    for index, row in df.iterrows():
        cik = row['cik']
        filing_year = row['filingyear']

        print(f"\nProcessing CIK: {cik}, Year: {filing_year}")

        filing_url, filing_date = get_10k_url(cik, filing_year)

        if not filing_url:
            output_rows.append({'cik': cik, 'filingyear': filing_year, 'filingdate': None, 'reportingdate': None, 'riskfactortitle': None})
            continue

        try:
            time.sleep(0.1)
            response = requests.get(filing_url, headers=HEADERS)
            response.raise_for_status()
            html = response.text
        except Exception as e:
            print(f"Failed to download 10-K: {e}")
            output_rows.append({'cik': cik, 'filingyear': filing_year, 'filingdate': filing_date, 'reportingdate': None, 'riskfactortitle': None})
            continue

        soup = BeautifulSoup(html, 'html.parser')
        section_soup = extract_risk_section(html, soup, cik, filing_year)
        risk_titles = identify_risk_factors(section_soup, cik, filing_year)
        reporting_date = get_reporting_date(html, filing_year)

        if not risk_titles:
            output_rows.append({'cik': cik, 'filingyear': filing_year, 'filingdate': filing_date, 'reportingdate': reporting_date, 'riskfactortitle': None})
        else:
            for title in risk_titles:
                output_rows.append({'cik': cik, 'filingyear': filing_year, 'filingdate': filing_date, 'reportingdate': reporting_date, 'riskfactortitle': title})

    output_df = pd.DataFrame(output_rows)
    output_df.to_csv(output_csv, index=False)
    print(f"\nFinished processing. Results saved to {output_csv}")

if __name__ == "__main__":
    main()
