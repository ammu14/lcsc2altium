# -*- coding: utf-8 -*-
import urllib.request

url = ("https://raw.githubusercontent.com/jrsoftware/issrc/"
       "refs/heads/main/Files/Languages/ChineseSimplified.isl")
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=60) as r:
    data = r.read()
out = ".tools/innosetup/Languages/ChineseSimplified.isl"
open(out, "wb").write(data)
print("OK", len(data), "bytes ->", out)
