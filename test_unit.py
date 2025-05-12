from unit import square

def main():
    test_square()

def test_square():
    assert square(2) == 4, "Test case failed: square(2) should return 4"
    assert square(-3) == 9, "Test case failed: square(-3) should return -6"
    assert square(0) == 0, "Test case failed: square(0) should return 0"
    print("All test cases passed!")

if __name__ == "__main__":
    main()
    