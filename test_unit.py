from unit import square


def test_square():
    assert square(2) == 4
    assert square(3) == 6
    assert square(0) == 0