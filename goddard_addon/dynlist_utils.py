import re
import ast

def tokenize_list(dynlist):
    arr_start = dynlist.find("{")
    arr_end = dynlist.find("}") + 1
    tokens = dynlist[arr_start:arr_end]

    tokens = re.sub(r"//(.+?)\n", r"\n", tokens, 0)
    tokens = tokens.replace("{", "[").replace("}", "]")
    tokens = tokens.replace("(", ", (").replace(" ", "")
    tokens = re.sub(r"([a-wyzA-WYZ_\&][a-wyzA-WYZ_0-9]{3,100})", r"'\1'", tokens, 0)
    tokens = tokens.replace(",\n", "],\n").replace("\n'", "\n['")
    tokens = ast.literal_eval(tokens)

    return tokens