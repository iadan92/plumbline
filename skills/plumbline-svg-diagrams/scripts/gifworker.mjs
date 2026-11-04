// Worker for raster.mjs: draws one SVG frame per message so a GIF renders on every core.
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { parentPort, workerData } from "node:worker_threads";

const require = createRequire(path.join(workerData.modules, "package.json"));
const { Resvg } = require("@resvg/resvg-js");

parentPort.on("message", ({ i, file }) => {
  const svg = fs.readFileSync(file, "utf8");
  const probe = new Resvg(svg).width;
  const fitTo = workerData.maxWidth && probe > workerData.maxWidth ? { mode: "width", value: workerData.maxWidth } : { mode: "zoom", value: 1 };
  const img = new Resvg(svg, { fitTo, font: { loadSystemFonts: true }, background: workerData.background }).render();
  const pixels = new Uint8Array(img.pixels);
  parentPort.postMessage({ i, pixels, width: img.width, height: img.height }, [pixels.buffer]);
});
