import re

def check_file(fname):
    with open(fname, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    curly = 0
    paren = 0
    bracket = 0
    for idx, line in enumerate(lines, 1):
        # strip string literals and comments
        clean = re.sub(r'//.*', '', line)
        clean = re.sub(r'/\*.*?\*/', '', clean)
        clean = re.sub(r"'(\\.|[^'])*'", "''", clean)
        clean = re.sub(r'"(\\.|[^"])*"', '""', clean)
        clean = re.sub(r'`(\\.|[^`])*`', '``', clean)
        for ch in clean:
            if ch == '{': curly += 1
            elif ch == '}':
                curly -= 1
                if curly < 0:
                    print(f"Error in {fname}: Unexpected '}}' at line {idx}")
                    curly = 0
            elif ch == '(': paren += 1
            elif ch == ')':
                paren -= 1
                if paren < 0:
                    print(f"Error in {fname}: Unexpected ')' at line {idx}")
                    paren = 0
            elif ch == '[': bracket += 1
            elif ch == ']':
                bracket -= 1
                if bracket < 0:
                    print(f"Error in {fname}: Unexpected ']' at line {idx}")
                    bracket = 0
    print(f"{fname} -> curly: {curly}, paren: {paren}, bracket: {bracket}")

check_file('static/js/terminal.js')
check_file('static/js/dashboard.js')
