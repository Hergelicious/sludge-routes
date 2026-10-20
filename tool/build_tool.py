
import json
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

body = open(os.path.join(HERE, "page.html"), encoding="utf-8").read()
model = open(os.path.join(HERE, "model.js"), encoding="utf-8").read()
params = open(os.path.join(HERE, "params.json"), encoding="utf-8").read()
c = pd.read_csv(os.path.join(ROOT, "data", "countries.csv"))
countries = [dict(iso=r.iso, name=r.country.replace("Turkey", "Türkiye"), ef=float(r.grid_tco2_per_mwh),
                  diesel=float(r.diesel_usd_l), elec=float(r.elec_price_usd_kwh)) for r in c.itertuples()]
countries.sort(key=lambda d: d["name"])
disposal = pd.read_csv(os.path.join(ROOT, "data", "disposal.csv"))
disp = {r.key: dict(land=r.land, landfill=r.landfill, incin=r.incin, other=r.other) for r in disposal.itertuples() if "_" not in r.key}

inject = (f"<script>\n{model}\n</script>\n<script>\nconst PARAMS = {params};\nconst COUNTRIES = {json.dumps(countries)};\n"
          f"const DISPOSAL = {json.dumps(disp)};\nSludgeModel.init(PARAMS);\n</script>\n")
page = body.replace("<!-- MODEL -->", inject)
open(os.path.join(HERE, "page_built.html"), "w", encoding="utf-8").write(page)
full = ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
        + page.split("<!-- BODY -->")[0] + "</head>\n<body>\n" + page.split("<!-- BODY -->")[1] + "\n</body>\n</html>\n")
open(os.path.join(HERE, "index.html"), "w", encoding="utf-8").write(full)
print("built tool/index.html and tool/page_built.html", len(full) // 1024, "kB")
