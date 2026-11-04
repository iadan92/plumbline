// Rasterise SVG files to PNG, PDF or an animated GIF. Called by export.py, which installs the two
// packages it needs (@resvg/resvg-js and gifenc) once and passes their location.
//
// node raster.mjs --modules DIR --mode png|pdf|gif --out FILE [--scale 2] [--max-width 1200] [--fps 12]
//                 [--colors 128] [--background "#ffffff"] input.svg [more frames.svg ...]
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import zlib from "node:zlib";
import { Worker } from "node:worker_threads";

const args = process.argv.slice(2);
const opt = { scale: "2", "max-width": "0", fps: "12", colors: "128", background: "" };
const files = [];
for (let i = 0; i < args.length; i++) {
  if (args[i].startsWith("--")) opt[args[i].slice(2)] = args[++i];
  else files.push(args[i]);
}
const need = (name) => {
  if (!opt[name]) throw new Error(`missing --${name}`);
  return opt[name];
};
const require = createRequire(path.join(need("modules"), "package.json"));
const { Resvg } = require("@resvg/resvg-js");

function draw(file, { scale, maxWidth, background }) {
  const svg = fs.readFileSync(file, "utf8");
  const probe = new Resvg(svg).width;
  const fitTo = maxWidth && probe > maxWidth ? { mode: "width", value: maxWidth } : { mode: "zoom", value: scale };
  const resvg = new Resvg(svg, { fitTo, font: { loadSystemFonts: true }, ...(background ? { background } : {}) });
  return resvg.render();
}

function pdf(rgba, w, h, pxW, pxH) {
  // raster page: RGB pixels (alpha flattened onto white) in one image the size of the page
  const rgb = Buffer.alloc(w * h * 3);
  for (let i = 0, j = 0; i < w * h * 4; i += 4, j += 3) {
    const a = rgba[i + 3] / 255;
    for (let c = 0; c < 3; c++) rgb[j + c] = Math.round(rgba[i + c] * a + 255 * (1 - a));
  }
  const data = zlib.deflateSync(rgb);
  const pw = (pxW * 0.75).toFixed(2), ph = (pxH * 0.75).toFixed(2);
  const content = Buffer.from(`q ${pw} 0 0 ${ph} 0 0 cm /Im0 Do Q`);
  const parts = [];
  const offsets = [];
  let size = 0;
  const push = (b) => { const buf = Buffer.isBuffer(b) ? b : Buffer.from(b, "latin1"); parts.push(buf); size += buf.length; };
  const obj = (n, body, stream) => {
    offsets[n] = size;
    push(`${n} 0 obj\n${body}\n`);
    if (stream) { push("stream\n"); push(stream); push("\nendstream\n"); }
    push("endobj\n");
  };
  push("%PDF-1.4\n");
  obj(1, "<< /Type /Catalog /Pages 2 0 R >>");
  obj(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
  obj(3, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pw} ${ph}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>`);
  obj(4, `<< /Type /XObject /Subtype /Image /Width ${w} /Height ${h} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length ${data.length} >>`, data);
  obj(5, `<< /Length ${content.length} >>`, content);
  const xref = size;
  push(`xref\n0 6\n0000000000 65535 f \n${[1, 2, 3, 4, 5].map((n) => String(offsets[n]).padStart(10, "0") + " 00000 n \n").join("")}`);
  push(`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
  return Buffer.concat(parts);
}

const mode = need("mode");
const out = need("out");
const scale = Number(opt.scale);
const maxWidth = Number(opt["max-width"]);
if (!files.length) throw new Error("no input SVG files");

if (mode === "png") {
  const img = draw(files[0], { scale, maxWidth, background: opt.background });
  fs.writeFileSync(out, img.asPng());
  console.log(`wrote ${out} (${img.width}x${img.height})`);
} else if (mode === "pdf") {
  const img = draw(files[0], { scale, maxWidth: 0, background: "#ffffff" });
  fs.writeFileSync(out, pdf(img.pixels, img.width, img.height, img.width / scale, img.height / scale));
  console.log(`wrote ${out} (${img.width}x${img.height} pixels on one page)`);
} else if (mode === "gif") {
  const { GIFEncoder, quantize, applyPalette } = require("gifenc");
  const background = opt.background || "#ffffff";
  const pool = Array.from({ length: Math.max(1, Math.min(os.cpus().length, 8, files.length)) }, () =>
    new Worker(new URL("./gifworker.mjs", import.meta.url), { workerData: { modules: need("modules"), maxWidth, background } }));
  // draw the listed frames on all cores; results come back by index
  const drawAll = (indexes, each) => new Promise((resolve, reject) => {
    let next = 0, done = 0;
    const feed = (w) => { if (next < indexes.length) w.postMessage({ i: indexes[next], file: files[indexes[next++]] }); };
    for (const w of pool) {
      w.removeAllListeners("message");
      w.on("error", reject);
      w.on("message", (m) => { each(m); if (++done === indexes.length) resolve(); else feed(w); });
      feed(w);
    }
  });
  // one palette for the whole loop: diagrams use few flat colours, so a sample of the frames covers them
  const step = Math.max(1, Math.floor(files.length / 8));
  const sampled = [];
  await drawAll(files.map((_, i) => i).filter((i) => i % step === 0), (m) => sampled.push(Buffer.from(m.pixels)));
  const palette = [[0, 0, 0], ...quantize(Buffer.concat(sampled), Number(opt.colors) - 1, { format: "rgb444" })];   // index 0 stays transparent
  const delay = Math.max(20, Math.round(1000 / Number(opt.fps) / 10) * 10);
  const gif = GIFEncoder();
  const results = new Map();
  let nextOut = 0, prev = null, width = 0, height = 0;
  await drawAll(files.map((_, i) => i), (m) => {
    results.set(m.i, m);
    while (results.has(nextOut)) {                       // write in order, as soon as the next frame is ready
      const f = results.get(nextOut);
      results.delete(nextOut);
      width = f.width; height = f.height;
      const idx = applyPalette(f.pixels, palette.slice(1), "rgb444").map((v) => v + 1);
      const cur = Uint8Array.from(idx);
      // pixels that did not change since the previous frame become transparent, so each frame stores only the motion
      if (prev) for (let k = 0; k < idx.length; k++) if (idx[k] === prev[k]) idx[k] = 0;
      gif.writeFrame(idx, width, height, nextOut === 0
        ? { palette, delay, repeat: 0 }
        : { delay, transparent: true, transparentIndex: 0, dispose: 1 });
      prev = cur;
      nextOut++;
    }
  });
  pool.forEach((w) => w.terminate());
  gif.finish();
  fs.writeFileSync(out, gif.bytes());
  console.log(`wrote ${out} (${width}x${height}, ${files.length} frames, ${(gif.bytes().length / 1024).toFixed(0)} KB)`);
} else {
  throw new Error(`unknown mode ${mode}`);
}
