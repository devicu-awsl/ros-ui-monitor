from app.routeros import parsers


def test_parse_bool():
    assert parsers.parse_bool("true") is True
    assert parsers.parse_bool("false") is False
    assert parsers.parse_bool("yes") is True
    assert parsers.parse_bool(None) is None
    assert parsers.parse_bool("garbage") is None


def test_parse_percent():
    assert parsers.parse_percent("23%") == 23.0
    assert parsers.parse_percent("0%") == 0.0
    assert parsers.parse_percent("7") == 7.0
    assert parsers.parse_percent(None) is None


def test_parse_size():
    assert parsers.parse_size("94.2MiB") == int(94.2 * 1024**2)
    assert parsers.parse_size("1024") == 1024
    assert parsers.parse_size("1KiB") == 1024
    assert parsers.parse_size("2GiB") == 2 * 1024**3
    assert parsers.parse_size("weird") is None


def test_parse_duration():
    assert parsers.parse_duration("2d20h12m20s") == 2 * 86400 + 20 * 3600 + 12 * 60 + 20
    assert parsers.parse_duration("1w") == 604800
    assert parsers.parse_duration("500ms") == 0.5
    assert parsers.parse_duration("45") == 45.0
    assert parsers.parse_duration(None) is None


def test_parse_rate():
    assert parsers.parse_rate("100Mbps") == 100_000_000
    assert parsers.parse_rate("1Gbps") == 1_000_000_000
    assert parsers.parse_rate("2500") == 2500
    assert parsers.parse_rate("nope") is None


def test_parse_temperature():
    assert parsers.parse_temperature("42C") == 42.0
    assert parsers.parse_temperature("38") == 38.0
    assert parsers.parse_temperature(None) is None
