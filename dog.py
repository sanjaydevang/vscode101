def main():
    number = get_number()
    bark(3)


def get_number():
    while True:
        try:
            number = int(input("Enter a number: "))
            if number > 0:
                return number
        except ValueError:
            print("Invalid input. Please enter a valid number.")

def bark(n):
    for i in range(n):
        print("Bark!")


main()
        