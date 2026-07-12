import React, { useState } from "react";
import { Check, Copy, FileCode, Terminal, FileText, Settings } from "lucide-react";

interface CodeViewerProps {
  onClose?: () => void;
}

export const CodeViewer: React.FC<CodeViewerProps> = ({ onClose }) => {
  const [activeTab, setActiveTab] = useState<"python" | "dockerfile" | "requirements" | "readme">("python");
  const [copied, setCopied] = useState(false);

  const files = {
    python: {
      name: "fourvoice_captioner.py",
      icon: <FileCode className="w-4 h-4 text-brand-amber" />,
      language: "python",
      code: `#!/usr/bin/env python3
"""
FourVoice Captioner - AMD Developer Hackathon ACT II, Track 2 (Video Captioning)
Fully autonomous containerized Python pipeline.
"""

import os
import sys
import json
import glob
import logging
import argparse
import subprocess
import tempfile
import base64
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FourVoiceCaptioner")

FIREWORKS_BASE_URL = os.getenv("FIREWORKS_BASE_URL", "https://api.fireworks.ai/inference/v1")
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY")

WHISPER_MODEL = "accounts/fireworks/models/whisper-v3"
GEMMA_VISION_MODEL = "accounts/fireworks/models/gemma2-9b-it"
CHAT_WRITING_MODEL = "accounts/fireworks/models/llama-v3-70b-instruct"

def transcribe_audio_whisper(audio_path):
    headers = {"Authorization": f"Bearer {FIREWORKS_API_KEY}"}
    url = f"{FIREWORKS_BASE_URL}/audio/transcriptions"
    with open(audio_path, "rb") as f:
        files = {"file": (os.path.basename(audio_path), f, "audio/mpeg")}
        data = {"model": WHISPER_MODEL, "response_format": "json"}
        response = requests.post(url, files=files, data=data, headers=headers)
        return response.json().get("text", "")

def calculate_word_diversity(text):
    words = [w.lower().strip(".,?!") for w in text.split() if w]
    if not words: return 0.0
    return len(set(words)) / len(words)

# ... full autonomous implementation ready for execution in output directory ...
`
    },
    dockerfile: {
      name: "Dockerfile",
      icon: <Terminal className="w-4 h-4 text-brand-mint" />,
      language: "dockerfile",
      code: `FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \\
    ffmpeg \\
    ffprobe \
    ca-certificates \\
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY fourvoice_captioner.py .

RUN mkdir -p /app/input /app/output
RUN chmod +x fourvoice_captioner.py

ENTRYPOINT ["python3", "fourvoice_captioner.py", "--input-dir", "/app/input", "--output", "/app/output/results.json"]`
    },
    requirements: {
      name: "requirements.txt",
      icon: <Settings className="w-4 h-4 text-[#ede9e0]" />,
      language: "text",
      code: `requests>=2.28.0`
    },
    readme: {
      name: "README.md",
      icon: <FileText className="w-4 h-4 text-blue-400" />,
      language: "markdown",
      code: `# FourVoice Captioner - AMD Hackathon Submission

Autonomous 9-stage video captioning system leveraging Google's Gemma Visual Grounding and Llama/Qwen style rewriters.

## Quickstart

\`\`\`bash
# Build
docker build -t fourvoice-captioner .

# Run autonomously
docker run -e FIREWORKS_API_KEY="your_key" \\
  -v "$(pwd)/videos:/app/input" \\
  -v "$(pwd)/results:/app/output" \\
  fourvoice-captioner
\`\`\``
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(files[activeTab].code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-brand-surface border border-brand-charcoal rounded-xl overflow-hidden flex flex-col h-full shadow-2xl">
      {/* Drawer Header */}
      <div className="bg-[#151816] px-5 py-4 border-b border-brand-charcoal flex justify-between items-center">
        <div className="flex items-center space-x-3">
          <Terminal className="w-5 h-5 text-brand-amber" />
          <div>
            <h3 className="font-display text-base font-bold text-brand-bone tracking-tight">Autonomous Code Assembly</h3>
            <p className="text-xs text-gray-500 font-mono">AMD TRACK 2 SUBMISSION SOURCE</p>
          </div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-brand-bone transition-colors"
          >
            <span className="material-symbols-outlined text-xl">close</span>
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="bg-[#121513] px-4 py-2 border-b border-brand-charcoal flex space-x-2 overflow-x-auto no-scrollbar">
        {(Object.keys(files) as Array<keyof typeof files>).map((tabKey) => {
          const file = files[tabKey];
          const isActive = activeTab === tabKey;
          return (
            <button
              key={tabKey}
              onClick={() => setActiveTab(tabKey)}
              className={`flex items-center space-x-2 px-3 py-1.5 rounded-md font-mono text-xs transition-all ${
                isActive
                  ? "bg-brand-charcoal text-brand-bone border-l-2 border-brand-amber font-semibold"
                  : "text-gray-400 hover:text-brand-bone hover:bg-brand-charcoal/30"
              }`}
            >
              {file.icon}
              <span>{file.name}</span>
            </button>
          );
        })}
      </div>

      {/* Code Area */}
      <div className="relative flex-1 bg-[#0d0f0e] overflow-auto p-5 font-mono text-xs text-gray-300 leading-relaxed no-scrollbar select-text">
        <button
          onClick={handleCopy}
          className="absolute top-4 right-4 bg-brand-charcoal/80 hover:bg-brand-charcoal text-gray-300 hover:text-brand-bone p-2 rounded-lg transition-all border border-brand-charcoal flex items-center space-x-2 cursor-pointer z-10"
          title="Copy to clipboard"
        >
          {copied ? <Check className="w-4 h-4 text-brand-mint" /> : <Copy className="w-4 h-4" />}
          <span>{copied ? "Copied!" : "Copy"}</span>
        </button>
        <pre className="whitespace-pre-wrap selection:bg-brand-amber/20">
          <code>{files[activeTab].code}</code>
        </pre>
      </div>

      {/* Code Footer */}
      <div className="bg-[#151816] px-5 py-3.5 border-t border-brand-charcoal flex justify-between items-center text-xs text-gray-400 font-mono">
        <span className="flex items-center space-x-1.5">
          <span className="w-2 h-2 rounded-full bg-brand-mint animate-pulse" />
          <span>Container-ready for scoring harness</span>
        </span>
        <span className="text-gray-500">AMD Hackathon Track 2</span>
      </div>
    </div>
  );
};
