from app.parser import detect_domain, parse_free_text


def test_detect_furniture():
    assert detect_domain("Стол офисный ДСП") == "furniture"


def test_detect_tools():
    assert detect_domain("дрель шуруповерт аккумуляторная") == "tools"


def test_parse_pipeline_style():
    product, kvs = parse_free_text(
        "Стол офисный | Материал ДСП | Высота 750 мм | Цвет серый"
    )
    assert "стол" in product.lower()
    names = {k.name.lower() for k in kvs}
    assert "материал" in names or any("дсп" in k.value.lower() for k in kvs)
    assert any(k.name.lower() == "высота" for k in kvs)


def test_parse_free_sentence():
    product, kvs = parse_free_text("стол офисный дсп высота 750 мм цвет серый")
    assert product
    assert any(k.name.lower() == "высота" for k in kvs)
    assert any(k.name.lower() == "цвет" for k in kvs)
