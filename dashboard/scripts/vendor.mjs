// Copy the deck.gl UMD bundle into vendor/ so the dashboard runs with no build step and no internet.
import { copyFileSync, mkdirSync, readFileSync } from "node:fs";

const version = JSON.parse(readFileSync("node_modules/deck.gl/package.json", "utf8")).version;
mkdirSync("vendor", { recursive: true });
copyFileSync("node_modules/deck.gl/dist.min.js", `vendor/deck.gl-${version}.min.js`);
console.log(`vendored deck.gl ${version}`);
