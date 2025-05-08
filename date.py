from datetime import datetime

def say_day_of_week(date):
    try:
        day_of_week = datetime.strptime(date, "%Y-%m-%d").strftime("%A")
        print(f"The day of the week for {date} is {day_of_week}.")
    except ValueError:
        print("Invalid date format. Please use YYYY-MM-DD.")

say_day_of_week("2023-10-01")