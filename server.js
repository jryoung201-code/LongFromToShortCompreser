const cors = require('cors');
const express = require('express');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { randomUUID } = require('crypto');
const { spawn } = require('child_process');
const multer = require('multer');

const app = express();
const port = Number(process.env.PORT) || 3000;
const uploadDir = path.join(os.tmpdir(), 'reel-cutter-uploads');
const outputDir = path.join(os.tmpdir(), 'reel-cutter-outputs');
const allowedHeights = new Set([480, 720, 1080]);

fs.mkdirSync(uploadDir, { recursive: true });
fs.mkdirSync(outputDir, { recursive: true });

app.use(cors());

const upload = multer({
  dest: uploadDir,
  limits: { fileSize: 1024 * 1024 * 1024 }
});

function removeFile(filePath) {
  if (filePath) fs.promises.unlink(filePath).catch(() => {});
}

function runFfmpeg(inputPath, outputPath, height) {
  return new Promise((resolve, reject) => {
    const ffmpeg = spawn('ffmpeg', [
      '-hide_banner',
      '-loglevel', 'error',
      '-i', inputPath,
      '-vf', `scale=-2:${height}`,
      '-c:v', 'libx264',
      '-preset', process.env.FFMPEG_PRESET || 'veryfast',
      '-crf', process.env.FFMPEG_CRF || '26',
      '-c:a', 'aac',
      '-b:a', '128k',
      '-movflags', '+faststart',
      '-y',
      outputPath
    ]);
    let error = '';

    ffmpeg.stderr.on('data', (chunk) => { error += chunk.toString(); });
    ffmpeg.on('error', reject);
    ffmpeg.on('close', (code) => {
      if (code === 0) resolve();
      else reject(new Error(error.trim() || `FFmpeg exited with code ${code}`));
    });
  });
}

app.get('/health', (_req, res) => {
  res.json({ ok: true, service: 'reel-cutter-compression' });
});

app.post('/compress', upload.single('video'), async (req, res) => {
  const inputPath = req.file?.path;
  let outputPath;

  try {
    if (!req.file) return res.status(400).json({ error: 'Attach a video using the video field.' });

    const height = Number(req.body.height || 720);
    if (!allowedHeights.has(height)) {
      return res.status(400).json({ error: 'height must be 480, 720, or 1080.' });
    }

    outputPath = path.join(outputDir, `${randomUUID()}.mp4`);
    await runFfmpeg(inputPath, outputPath, height);

    res.download(outputPath, `compressed_${height}p.mp4`, (error) => {
      removeFile(inputPath);
      removeFile(outputPath);
      if (error && !res.headersSent) res.status(500).json({ error: 'Could not send the compressed video.' });
    });
  } catch (error) {
    removeFile(inputPath);
    removeFile(outputPath);
    res.status(500).json({ error: error.message || 'Compression failed.' });
  }
});

app.use((error, _req, res, _next) => {
  if (error instanceof multer.MulterError && error.code === 'LIMIT_FILE_SIZE') {
    return res.status(413).json({ error: 'Video is larger than the 1GB upload limit.' });
  }
  res.status(500).json({ error: error.message || 'Server error.' });
});

app.listen(port, () => {
  console.log(`Compression server listening on http://localhost:${port}`);
});
