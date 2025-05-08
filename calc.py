x = input("Enter first number: ")
y = input("Enter second number: ")


z = float(x) / float(y)

z = round(z, 2)
print(f"after addition is  {z:,}")








def main():
    x = int(input("Enter first number: "))
    print("the values of x squared is ", square(x))

def square(x):
    return x * x
# Call the main function



main()