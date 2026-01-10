import json


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def loads(s):
    return json.loads(s)