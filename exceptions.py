while True:
    try:
        x = int(input("Enter a number: "))
        print(f"x value is {x}")
        break  # ✅ Valid input, exit loop
    except ValueError:
        print("Invalid input. Please enter a valid number.")
