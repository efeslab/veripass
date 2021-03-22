def verilog_string_to_int(s):
    value_pos = s.find("h")
    if value_pos >= 0:
        return int("0x"+s[value_pos+1:], 16)
    else:
        value_pos = s.find("b")
        if value_pos >= 0:
            return int("0b"+s[value_pos+1:], 16)
        else:
            value_pos = s.find("'")
            assert(value_pos == -1)
            return int(s)
