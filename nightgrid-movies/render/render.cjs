// Renders movies.html into webm files with ffmpeg (VP9, 30 fps, 1920x1080, no audio).
// usage: node render.cjs <outdir> [movie-id ...]      preview: node render.cjs --stills <outdir>
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const path = require("path"), fs = require("fs");
const FPS = 30;
(async () => {
  const args = process.argv.slice(2), stills = args[0] === "--stills"; if (stills) args.shift();
  const out = path.resolve(args.shift()); fs.mkdirSync(out, { recursive: true });
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  await p.goto("file://" + path.join(__dirname, "movies.html")); await p.evaluate(() => window.ready);
  const all = await p.evaluate(() => window.movies);
  for (const id of (args.length ? args : Object.keys(all))) {
    const n = Math.round(all[id] * FPS);
    if (stills) {
      for (let i = 0; i < 8; i++) { const f = Math.floor(i * (n - 1) / 7);
        await p.evaluate(([id, f]) => window.draw(id, f / 30, f), [id, f]);
        await p.screenshot({ path: `${out}/${id}-${String(f).padStart(3, "0")}.jpg`, type: "jpeg", quality: 70 }); }
      continue;
    }
    const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-i", "-",
      "-vf", "scale=1280:720:flags=lanczos", "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "42", "-pix_fmt", "yuv420p", "-row-mt", "1", "-deadline", "good", "-cpu-used", "3",
      "-an", path.join(out, `${id}.webm`)], { stdio: ["pipe", "inherit", "inherit"] });
    for (let f = 0; f < n; f++) {
      await p.evaluate(([id, f]) => window.draw(id, f / 30, f), [id, f]);
      const buf = await p.screenshot({ type: "png" });
      if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once("drain", r));
    }
    ff.stdin.end(); await new Promise((r, j) => ff.on("close", c => c ? j(new Error(`ffmpeg ${c}`)) : r()));
    console.log(id, n, "frames", (fs.statSync(path.join(out, `${id}.webm`)).size / 1e6).toFixed(2), "MB");
  }
  await b.close();
})();
