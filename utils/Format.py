import pyverilog.vparser.ast as vast

def beautify_name(name):
    s = name
    s = s.replace("__028", "(")
    s = s.replace("__029", ")")
    s = s.replace("__03A", ":")
    s = s.replace("__05F", "_")
    s = s.replace("__DOT__", ".")
    s = s.replace("__BRA__", "[")
    s = s.replace("__KET__", "]")
    return s

def format_name(name):
    s = name
    s = s.replace("(", "__028")
    s = s.replace(")", "__029")
    s = s.replace(":", "__03A")
    s = s.replace("__05F", "_")
    s = s.replace(".", "__DOT__")
    s = s.replace("[", "__BRA__")
    s = s.replace("]", "__KET__")
    return s
