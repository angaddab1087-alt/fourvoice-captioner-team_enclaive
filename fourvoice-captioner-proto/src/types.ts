/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export interface QCScore {
  captionType: string;
  accuracyScore: number; // 1-5
  styleScore: number;    // 1-5
  feedback: string;
}

export interface PipelineResults {
  video: string;
  formal: string;
  sarcastic: string;
  humorous_tech: string;
  humorous_non_tech: string;
  recommended_style: "formal" | "sarcastic" | "humorous_tech" | "humorous_non_tech";
  reasoning: string;
  confidence: number; // 0.0 to 1.0
  transcript?: string;
  wordCount?: number;
  isAudioInformative?: boolean;
  groundedDescription?: string;
  qcPasses?: QCScore[];
}

export interface SampleClip {
  id: string;
  title: string;
  category: "dialogue-heavy" | "music-video" | "silent-action" | "static-image-music" | "low-audio-ambiguous";
  description: string;
  thumbnailUrl: string;
  videoUrl?: string;
  // Pre-configured output fallback or simulation config
  presetResults: PipelineResults;
}
