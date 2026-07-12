import express from "express";
import path from "path";
import multer from "multer";
import { spawn } from "child_process";
import fs from "fs";
import os from "os";
import dotenv from "dotenv";

dotenv.config();

const PORT = parseInt(process.env.PORT || "3001", 10);

const logger = {
  info: (msg: string) => console.log(`[INFO] ${msg}`),
  warn: (msg: string) => console.warn(`[WARN] ${msg}`),
  error: (msg: string) => console.error(`[ERROR] ${msg}`),
};

// In-memory progress store (simple, single-user demo)
const progressStore = new Map<string, { stage: string; progress: number; done: boolean }>();

function setProgress(jobId: string, stage: string, progress: number, done = false) {
  progressStore.set(jobId, { stage, progress, done });
  // Auto-cleanup after 5 minutes
  setTimeout(() => progressStore.delete(jobId), 5 * 60 * 1000);
}

function getProgress(jobId: string) {
  return progressStore.get(jobId) || { stage: "unknown", progress: 0, done: false };
}

// PRESET_CLIPS: labeled sample demo clips for instant UI preview
const PRESET_CLIPS: Record<string, object> = {
  tech_tutorial: {
    video: "tech_tutorial.mp4",
    formal:
      "In this tutorial, the instructor demonstrates the proper procedure to set up a modern web application framework, highlighting directory structures and configuration commands.",
    sarcastic:
      "Oh great, another programming framework to learn. Just what our Friday night plans were missing.",
    humorous_tech:
      "Upgrading to this new framework so you can compile 0.4 seconds faster, just to spend 3 hours debugging a missing semicolon.",
    humorous_non_tech:
      "Trying to understand coding tutorials is like listening to someone explain a recipe for a dish you have never heard of, using words they made up.",
    recommended_style: "humorous_tech",
    reasoning:
      "The video focuses strictly on technical developer instructions, which aligns perfectly with dev-culture humor.",
    confidence: 0.94,
  },
  concert_clip: {
    video: "concert_clip.mp4",
    formal:
      "The video presents footage of a live musical performance with flashing stage lights and active audience engagement.",
    sarcastic:
      "Paying $300 to stand in a sweaty crowd of 50,000 people and watch a concert through the screen of the phone in front of you. Truly majestic.",
    humorous_tech:
      "This concert lighting has more sync transitions and flashing states than my entire production codebase on a deploy cycle.",
    humorous_non_tech:
      "Nothing says 'I love live music' like holding your phone perfectly still for two hours so you can capture a video you'll never watch again.",
    recommended_style: "humorous_non_tech",
    reasoning:
      "The clip is highly visual, energetic, and relatable to general concert-goers, making everyday humor the natural fit.",
    confidence: 0.68,
  },
  skate_stunt: {
    video: "skate_stunt.mp4",
    formal:
      "An athlete on a skateboard performs a mid-air rotation trick over a set of concrete steps in an urban plaza setting.",
    sarcastic:
      "Gravity called and begged this skater to stop embarrassing it in public. Truly disrespectful to Newtonian physics.",
    humorous_tech:
      "Executing a flawless kickflip on the first try is equivalent to deploying a new backend service and seeing a 200 OK without any warnings.",
    humorous_non_tech:
      "My joints are hurting just watching this person jump down ten concrete stairs for fun.",
    recommended_style: "sarcastic",
    reasoning:
      "The high-adrenaline, effortless-looking nature of the stunt benefits from a witty, dry reaction.",
    confidence: 0.76,
  },
  comic_reel: {
    video: "comic_reel.mp4",
    formal:
      "The video displays a static digital illustration rendered in a retro comic book style, paired with a repeating instrumental music loop.",
    sarcastic:
      "Congratulations to the editor who figured out that adding a slow zoom to a single drawing qualifies as a high-production video.",
    humorous_tech:
      "This video has fewer visual updates and state changes than a static index.html file hosted on a 2g network.",
    humorous_non_tech:
      "When you want to read a comic book but you're too tired to turn the pages, so you let a video do it for you.",
    recommended_style: "formal",
    reasoning:
      "Given the static nature of the asset, a straightforward, formal documentation of the visual style is highly appropriate.",
    confidence: 0.62,
  },
  ambient_nature: {
    video: "ambient_nature.mp4",
    formal:
      "A serene woodland scene depicting wind rustling through dense green foliage with faint sounds of distant wildlife.",
    sarcastic:
      "Behold, leaves. Doing absolutely nothing but shaking in the wind. Pure, unadulterated high-octane thriller content.",
    humorous_tech:
      "Watching grass rustle is the ultimate therapeutic buffer to clear your cache after spending eight hours reviewing legacy code.",
    humorous_non_tech:
      "Me searching for peace and quiet in nature, only to spend the entire walk thinking about what I'm going to eat for dinner.",
    recommended_style: "humorous_non_tech",
    reasoning:
      "The relaxing, simple natural imagery pairs wonderfully with broad, casual everyday-life humor.",
    confidence: 0.82,
  },
};

/** Normalize pipeline output — flat fields or nested captions object */
function normalizePipelineResult(raw: Record<string, unknown>) {
  const captions = (raw.captions as Record<string, string>) || {};
  const out: Record<string, unknown> = { ...raw };

  for (const style of ["formal", "sarcastic", "humorous_tech", "humorous_non_tech"] as const) {
    const flat = raw[style];
    const nested = captions[style];
    const value =
      typeof flat === "string" && flat.trim()
        ? flat.trim()
        : typeof nested === "string" && nested.trim()
          ? nested.trim()
          : "";
    out[style] = value;
  }

  if (typeof out.recommended_style === "string") {
    out.recommended_style = (out.recommended_style as string).replace(/-/g, "_");
  }

  // Pass through timing and debugging info
  if (raw.timings) out.timings = raw.timings;
  if (raw.grounding_branch) out.grounding_branch = raw.grounding_branch;
  if (raw.transcript_preview) out.transcript_preview = raw.transcript_preview;
  if (raw.factual_description_preview) out.factual_description_preview = raw.factual_description_preview;

  return out;
}

const app = express();

// CORS for frontend on 5173
app.use((req, res, next) => {
  res.header("Access-Control-Allow-Origin", "http://localhost:5173");
  res.header("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.header("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") return res.sendStatus(200);
  next();
});

// Body parsers for API routes
app.use(express.json({ limit: "10mb" }));
app.use(express.urlencoded({ limit: "10mb", extended: true }));

// Configure multer for video file uploads (store in temp dir)
const upload = multer({
  dest: os.tmpdir(),
  limits: { fileSize: 2 * 1024 * 1024 * 1024 }, // 2GB max
  fileFilter: (_req, file, cb) => {
    const allowedMimes = [
      "video/mp4",
      "video/quicktime",
      "video/x-msvideo",
      "video/x-matroska",
      "video/webm",
    ];
    if (allowedMimes.includes(file.mimetype)) {
      cb(null, true);
    } else {
      cb(new Error(`Unsupported file type: ${file.mimetype}`));
    }
  },
});

/**
 * GET /api/progress
 * Returns current processing progress for the given jobId
 */
app.get("/api/progress", (req, res) => {
  const jobId = req.query.jobId as string;
  if (!jobId) return res.status(400).json({ error: "Missing jobId" });
  res.json(getProgress(jobId));
});

/**
 * POST /api/analyze
 *
 * Accepts either:
 *   - { sampleId: string } for preset demo clips (via JSON or form field)
 *   - multipart/form-data with "video" field for real video upload
 */
app.post("/api/analyze", upload.single("video"), async (req, res) => {
  try {
    // 1. Check for preset demo clip
    const sampleId = req.body?.sampleId;
    if (sampleId && PRESET_CLIPS[sampleId]) {
      logger.info(`Serving preset demo clip: ${sampleId}`);
      return res.json({
        success: true,
        source: "preset",
        data: PRESET_CLIPS[sampleId],
      });
    }

    // 2. Real video upload processing via Python pipeline
    if (!req.file) {
      return res
        .status(400)
        .json({ success: false, error: "No video file provided" });
    }

    const uploadedPath = req.file.path;
    const originalName = req.file.originalname;
    logger.info(`Received video upload: ${originalName} (${req.file.size} bytes)`);

    // Use jobId from frontend if provided, otherwise generate one
    const jobId = req.body?.jobId || `job_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    setProgress(jobId, "starting", 0);

    // Rename temp file to preserve extension (ffmpeg needs it)
    const ext = path.extname(originalName) || ".mp4";
    const renamedPath = uploadedPath + ext;
    fs.renameSync(uploadedPath, renamedPath);

    // Create temp directories for the pipeline
    const tempInputDir = fs.mkdtempSync(path.join(os.tmpdir(), "fv-input-"));
    const tempOutputDir = fs.mkdtempSync(path.join(os.tmpdir(), "fv-output-"));
    const videoDestination = path.join(tempInputDir, originalName);

    // Move file to input directory
    fs.renameSync(renamedPath, videoDestination);

    const outputPath = path.join(tempOutputDir, "results.json");

    // Spawn Python pipeline as subprocess
    const pythonCmd = process.platform === "win32" ? "python" : "python3";
    const pipelineScript = path.join(process.cwd(), "fourvoice_captioner.py");

    logger.info(`Spawning pipeline: ${pythonCmd} ${pipelineScript} --input-dir ${tempInputDir} --output ${outputPath}`);

    // Update progress: transcription stage
    setProgress(jobId, "transcription", 10);

    const result = await new Promise<{ success: boolean; data?: object; error?: string }>(
      (resolve) => {
        const proc = spawn(pythonCmd, [
          pipelineScript,
          "--input-dir",
          tempInputDir,
          "--output",
          outputPath,
        ], {
          env: { ...process.env },
          stdio: ["ignore", "pipe", "pipe"],
        });

        let stdout = "";
        let stderr = "";

        proc.stdout.on("data", (data: Buffer) => {
          const text = data.toString();
          stdout += text;
          text.split("\n").filter(Boolean).forEach((line: string) => {
            logger.info(`[PIPELINE] ${line}`);
            // Parse stage progress from pipeline logs
            if (line.includes("STAGE 1 complete")) setProgress(jobId, "transcription", 20);
            else if (line.includes("STAGE 2")) setProgress(jobId, "grounding", 35);
            else if (line.includes("STAGE 3")) setProgress(jobId, "grounding", 50);
            else if (line.includes("STAGE 4")) setProgress(jobId, "style_gen", 65);
            else if (line.includes("STAGE 5")) setProgress(jobId, "qc", 80);
            else if (line.includes("STAGE 6")) setProgress(jobId, "finalizing", 90);
            else if (line.includes("STAGE 7")) setProgress(jobId, "finalizing", 95);
            else if (line.includes("TIMING BREAKDOWN")) setProgress(jobId, "complete", 100, true);
          });
        });

        proc.stderr.on("data", (data: Buffer) => {
          const text = data.toString();
          stderr += text;
          text.split("\n").filter(Boolean).forEach((line: string) => {
            logger.warn(`[PIPELINE:stderr] ${line}`);
          });
        });

        proc.on("close", (code: number | null) => {
          if (code !== 0) {
            logger.error(`Pipeline exited with code ${code}`);
            logger.error(`Full stderr output:\n${stderr}`);
            logger.error(`Full stdout output:\n${stdout}`);
            setProgress(jobId, "error", 0, true);
            resolve({
              success: false,
              error: `Pipeline failed (exit code ${code}): ${(stderr.trim() || stdout.trim()).split('\n').slice(-5).join(' | ')}`,
            });
            return;
          }

          try {
            const resultsRaw = fs.readFileSync(outputPath, "utf-8");
            const resultsArray = JSON.parse(resultsRaw);

            if (Array.isArray(resultsArray) && resultsArray.length > 0) {
              setProgress(jobId, "complete", 100, true);
              resolve({ success: true, data: normalizePipelineResult(resultsArray[0] as Record<string, unknown>) });
            } else {
              resolve({
                success: false,
                error: "Pipeline produced no results",
              });
            }
          } catch (parseErr: any) {
            logger.error(`Failed to parse pipeline output: ${parseErr.message}`);
            resolve({
              success: false,
              error: "Failed to parse pipeline results",
            });
          }
        });

        // Timeout: 5 minutes max per video
        setTimeout(() => {
          proc.kill("SIGTERM");
          setProgress(jobId, "timeout", 0, true);
          resolve({ success: false, error: "Pipeline timed out (5 min)" });
        }, 5 * 60 * 1000);
      }
    );

    // Cleanup temp directories
    try {
      fs.rmSync(tempInputDir, { recursive: true, force: true });
      fs.rmSync(tempOutputDir, { recursive: true, force: true });
    } catch {
      // Best-effort cleanup
    }

    if (result.success) {
      return res.json({
        success: true,
        source: "pipeline",
        data: result.data,
      });
    } else {
      return res
        .status(500)
        .json({ success: false, error: result.error });
    }
  } catch (err: any) {
    logger.error(`Error in /api/analyze endpoint: ${err.message}`);
    res.status(500).json({ success: false, error: err.message });
  }
});

app.listen(PORT, "0.0.0.0", () => {
  logger.info(`[FourVoice Captioner API] Listening on http://localhost:${PORT}`);
  logger.info(`Environment: ${process.env.NODE_ENV || "development"}`);
  const apiKey = process.env.FIREWORKS_API_KEY;
  const baseUrl = process.env.FIREWORKS_BASE_URL;
  logger.info(`FIREWORKS_API_KEY: ${apiKey ? apiKey.substring(0, 8) + "..." + apiKey.substring(apiKey.length - 4) + " (" + apiKey.length + " chars)" : "NOT SET"}`);
  logger.info(`FIREWORKS_BASE_URL: ${baseUrl || "NOT SET (will default to https://api.fireworks.ai/inference/v1)"}`);
});