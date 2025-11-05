import re

PATTERN = r'\\cite\{([^\}]+?)\}'

with open('contents/1-introduction_cleaned.tex', 'r', encoding='utf-8') as f, open('contents/1-introduction_fixed.tex', 'w', encoding='utf-8') as out_f:
    for line in f:
        matches = re.findall(PATTERN, line)
        if matches:
            for match in matches:
                match_fixed = match.replace('，', ',')
                line = line.replace(f'\\cite{{{match}}}', f'\\cite{{{match_fixed}}}')
        out_f.write(line)