from app.preprocess import detect_script, preprocess


# --- The critical rule: newlines are the item delimiter ---

def test_newlines_are_preserved():
    text = "Fish fillet-5ctn\nPrawn meat -1ctn\nKing prawn-"
    out = preprocess(text)
    assert out == "Fish fillet-5ctn\nPrawn meat -1ctn\nKing prawn-"
    assert out.count("\n") == 2


def test_readme_example_7_keeps_its_line_structure():
    text = (
        "Boneless chicken 10kg\n"
        "Pork chop bone in 5kg\n"
        "Beef brisket 5kg\n"
        "Beef short plate 1mm 2kg\n"
        "\n"
        "Deliver 1 Oct"
    )
    out = preprocess(text)
    assert out.split("\n") == [
        "Boneless chicken 10kg",
        "Pork chop bone in 5kg",
        "Beef brisket 5kg",
        "Beef short plate 1mm 2kg",
        "Deliver 1 Oct",
    ]


# --- Whitespace rules ---

def test_double_spaces_collapse_to_one():
    assert preprocess("20  kg   of    rice") == "20 kg of rice"


def test_crlf_becomes_lf():
    assert preprocess("line one\r\nline two") == "line one\nline two"


def test_bare_cr_becomes_lf():
    assert preprocess("line one\rline two") == "line one\nline two"


def test_tabs_become_spaces():
    assert preprocess("Milo\t2kg") == "Milo 2kg"


def test_each_line_is_stripped():
    assert preprocess("   Coke 3ctn   \n   Eggs 5box  ") == "Coke 3ctn\nEggs 5box"


def test_blank_lines_are_dropped():
    assert preprocess("a\n\n\n\nb") == "a\nb"


def test_empty_input_returns_empty_string():
    assert preprocess("") == ""
    assert preprocess("   \n\n  \t ") == ""


def test_truncation_respects_max_chars():
    assert len(preprocess("a" * 500, max_chars=100)) == 100


# --- Unicode rules ---

def test_full_width_digits_are_normalized():
    assert preprocess("５箱苹果") == "5箱苹果"


def test_full_width_comma_is_normalized():
    assert "," in preprocess("我要订购5箱苹果，下星期一送去吉隆坡。")


def test_zero_width_characters_are_removed():
    assert preprocess("Mi\u200blo") == "Milo"


def test_mandarin_text_is_preserved():
    out = preprocess("我要订购5箱苹果")
    assert "苹果" in out


# --- What we deliberately do NOT do ---

def test_case_is_not_changed():
    assert preprocess("Jasmine Rice MILO") == "Jasmine Rice MILO"


def test_punctuation_is_not_stripped():
    out = preprocess("Can I get 3 cartons of Coke (1kg)?")
    assert "(1kg)?" in out


def test_hyphen_delimiters_survive():
    assert preprocess("Fish fillet-5ctn") == "Fish fillet-5ctn"


# --- Script detection ---
# This reports WRITING SYSTEMS, not languages. See detect_script's docstring.

def test_detect_latin():
    assert detect_script("20 kg of Jasmine rice") == "latin"


def test_detect_cjk():
    assert detect_script("我要订购5箱苹果") == "cjk"


def test_detect_both_scripts():
    assert detect_script("我要order 5 boxes of eggs") == "latin+cjk"


def test_a_chinese_message_with_a_brand_name_counts_as_both():
    """"我要5箱Milo" is a Chinese message, but the brand name is Latin script."""
    assert detect_script("我要5箱Milo") == "latin+cjk"


def test_traditional_characters_count_as_cjk():
    assert detect_script("我要訂購5箱蘋果") == "cjk"


def test_malay_is_reported_as_latin_not_english():
    """The honest limit of a character-range check: script, never language."""
    assert detect_script("Tolong hantar 5 ctn Milo ke Johor esok") == "latin"


def test_detect_none_when_there_are_no_letters():
    assert detect_script("") == "none"
    assert detect_script("123 456") == "none"
