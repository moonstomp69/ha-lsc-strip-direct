import importlib.util, pathlib
p = pathlib.Path(__file__).parents[1] / "custom_components/lsc_strip_direct/protocol.py"
s = importlib.util.spec_from_file_location("protocol", p)
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)

def test_white():
    assert m.encode_white(30, 0) == "AAAAFAAeAA=="
    assert m.encode_white(100, 100) == "AAAAFABkZA=="
    assert m.encode_white(1, 100) == "AAAAFAABZA=="
    assert m.encode_white(1, 0) == "AAAAFAABAA=="
    assert m.encode_white(1, 50) == "AAAAFAABMg=="
    assert m.decode_white("AAAAFAAeAA==") == (30, 0)
    assert m.encode_white(0, 150) == "AAAAFAABZA=="

def test_colour():
    assert m.encode_colour(120, 100, 100) == "007803e803e8"
    assert m.encode_colour(12, 100, 100) == "000c03e803e8"
    assert m.decode_colour("007803e803e8") == (120, 100.0, 100.0)
    assert m.decode_colour("zz") is None

def test_kelvin():
    assert m.kelvin_to_temp_pct(2700) == 0
    assert m.kelvin_to_temp_pct(6500) == 100
    assert m.temp_pct_to_kelvin(50) == 4600

if __name__ == "__main__":
    test_white(); test_colour(); test_kelvin(); print("ok")
