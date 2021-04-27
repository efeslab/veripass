import pyverilog.vparser.ast as vast

# a list of tuples, (to_escape, escaped)
escaping_rules = [
    ("'", "__027"),
    ("(", "__028"),
    (")", "__029"),
    (":", "__03A"),
    (".", "__DOT__"),
    ("[", "__BRA__"),
    ("]", "__KET__"),
]


def beautify_name(name):
    s = name
    for to_escape, escaped in escaping_rules:
        s = s.replace(escaped, to_escape)
    return s


def format_name(name):
    s = name
    for to_escape, escaped in escaping_rules:
        s = s.replace(to_escape, escaped)
    return s
