// node tool/parity_check.js  -> compares the JavaScript port with the Python results in parity.json
const fs = require("fs"), path = require("path");
const M = require("./model.js");
M.init(JSON.parse(fs.readFileSync(path.join(__dirname, "params.json"))));
const vec = JSON.parse(fs.readFileSync(path.join(__dirname, "parity.json")));
let n = 0, worst = 0, fails = 0;
const chk = (a, b, what) => { n++; const d = Math.abs(a - b); worst = Math.max(worst, d); if (d > 1e-9 * Math.max(1, Math.abs(b))) { fails++; if (fails < 10) console.log("MISMATCH", what, a, b); } };
for (const t of vec) {
  if (t.kind === "route") for (const r in t.out) chk(M.route(r, t.ef, t.p).total, t.out[r], "route " + r);
  if (t.kind === "value") for (const r in t.out) chk(M.value(r, t.ef, t.p, 0).market, t.out[r], "value " + r);
  if (t.kind === "state") for (const s in t.e) {
    chk(M.stateGhg(s === "-" ? "" : s, t.site, t.p), t.e[s], "stateGhg " + s);
    const c = M.stateCostParts(s === "-" ? "" : s, t.site, t.p); chk(c.other, t.cost[s][0], "cost " + s); chk(c.feed, t.cost[s][1], "feed " + s);
  }
  if (t.kind === "pyrocost") t.feeds.forEach((f, i) => chk(M.pyroCostPerTFeed(f, t.p), t.out[i], "pyrocost " + f));
}
console.log(`${n} values compared, ${fails} mismatches, largest difference ${worst.toExponential(2)}`);
process.exit(fails ? 1 : 0);
