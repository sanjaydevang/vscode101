from unit import square


def test_square():
    assert square(2) == 4
    assert square(3) == 6
    assert square(0) == 0

def test_square_negative():
    assert square(-2) == -4
    assert square(-3) == -6
    assert square(-1) == -2
def test_square_float():
    assert square(2.5) == 5.0
    assert square(3.5) == 7.0
    assert square(0.0) == 0.0
def test_square_negative_float():
    assert square(-2.5) == -5.0
    assert square(-3.5) == -7.0
    assert square(-1.0) == -2.0
def test_zero():
        assert square(0) == 0
        assert square(-0) == 0
        assert square(0.0) == 0.0
        assert square(-0.0) == 0.0