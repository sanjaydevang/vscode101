import pandas as pd
import csv
import os

# Create the sample input file with 10 CIKs and 3 years each
def create_input_file(filename):
    # 10 unique CIKs to use (including 1750 from your example)
    ciks = [1750, 320193, 789019, 1326801, 1018724, 1467858, 320187, 1800, 1318605, 1031296]
    
    # 3 years of filings per CIK
    years = [2016, 2017, 2018]
    
    # Create data for the CSV
    data = []
    for cik in ciks:
        for year in years:
            data.append({
                'cik': cik,
                'filingyear': year,
                'filingdate': '',  # Will be filled by the extraction script
                'reportingdate': '',  # Will be filled by the extraction script
                'rfdtitle': ''  # Will be filled by the extraction script
            })
    
    # Save to CSV
    df = pd.DataFrame(data)
    df.to_csv(filename, index=False)
    print(f"Created input file: {filename} with {len(data)} rows")
    return filename

# File name for the input file
input_filename = "rasamplemini_rfdtitle_9.csv"

# Create the input file
create_input_file(input_filename)

print("\nNow you can run the extraction script with the following inputs:")
print("Option: 2")
print(f"Input file: {input_filename}")
print("Output file: rasamplemini_rfdtitle_91.csv")