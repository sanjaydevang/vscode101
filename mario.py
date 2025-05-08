def main():
    size = int(input("Enter the size of the square: "))
    if size > 0:
        print_square(size)
    else:
        print("Size must be a positive integer.")
    

def print_square(size):
    for i in range(size):
        print("#" * size)

main()