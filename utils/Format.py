import pyverilog.vparser.ast as vast

# a list of tuples, (to_escape, escaped), to_escape should not duplicate
escaping_rules = [
    (".", "__DOT__"),
    ("[", "__BRA__"),
    ("]", "__KET__"),
    (" ", "__S__"),
]
ASCII_TRANSLATE_LIST = [ "'", "(", ")", ":", "+", "-", "*"]
for c in ASCII_TRANSLATE_LIST:
    escaping_rules.append((c, "__{:X}".format(ord(c))))
assert(len(set([x[0] for x in escaping_rules])) == len(escaping_rules) and \
    "escaping_rules should not contain duplicated rules")

def beautify_string(name):
    s = name
    for to_escape, escaped in escaping_rules:
        s = s.replace(escaped, to_escape)
    return s


def escape_string(name):
    s = name
    for to_escape, escaped in escaping_rules:
        s = s.replace(to_escape, escaped)
    return s
