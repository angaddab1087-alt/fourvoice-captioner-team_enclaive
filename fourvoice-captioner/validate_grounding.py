#!/usr/bin/env python3
"""
validate_grounding.py — Validation script for FourVoice Captioner grounding accuracy.

Methodology:
1. Run ffprobe to get duration/resolution
2. Extract frames at 2s intervals
3. Run the pipeline on the same video
4. Output a ground-truth timeline report and compare against pipeline claims
"""

import os
import sys
import json
import subprocess
import tempfile
import argparse


def probe_video(video_path):
    """Get video duration, resolution, and codec info via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)
    
    duration = float(info.get("format", {}).get("duration", 0))
    video_stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    width = video_stream.get("width", "?")
    height = video_stream.get("height", "?")
    codec = video_stream.get("codec_name", "?")
    fps = video_stream.get("r_frame_rate", "?")
    
    return {
        "duration_sec": round(duration, 2),
        "resolution": f"{width}x{height}",
        "codec": codec,
        "fps": fps,
        "file_size_bytes": int(info.get("format", {}).get("size", 0)),
    }


def extract_validation_frames(video_path, output_dir, interval_sec=2.0):
    """Extract frames at fixed intervals for manual validation."""
    probe = probe_video(video_path)
    duration = probe["duration_sec"]
    
    os.makedirs(output_dir, exist_ok=True)
    timestamps = []
    frame_paths = []
    
    t = 0.0
    idx = 0
    while t < duration:
        frame_name = f"val_frame_{idx:03d}_{t:.1f}s.jpg"
        frame_path = os.path.join(output_dir, frame_name)
        cmd = [
            "ffmpeg", "-y", "-ss", str(t), "-i", video_path,
            "-vframes", "1", "-vf", "scale='min(1024,iw)':-1",
            "-q:v", "2", frame_path,
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(frame_path):
            frame_paths.append(frame_path)
            timestamps.append(t)
        t += interval_sec
        idx += 1
    
    return probe, frame_paths, timestamps


def run_pipeline(video_path):
    """Run the fourvoice_captioner pipeline and return results."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    captioner_path = os.path.join(script_dir, "fourvoice_captioner.py")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        input_dir = os.path.join(tmpdir, "input")
        os.makedirs(input_dir)
        # Symlink or copy video
        link_path = os.path.join(input_dir, os.path.basename(video_path))
        try:
            os.symlink(os.path.abspath(video_path), link_path)
        except (OSError, NotImplementedError):
            import shutil
            shutil.copy2(video_path, link_path)
        
        output_path = os.path.join(tmpdir, "results.json")
        cmd = [
            sys.executable, captioner_path,
            "--input-dir", input_dir,
            "--output", output_path,
        ]
        print(f"Running pipeline: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            print(f"Pipeline stderr:\n{result.stderr[-2000:]}")
            return None
        
        if os.path.exists(output_path):
            with open(output_path) as f:
                return json.load(f)
    return None


def generate_report(video_path, probe_info, pipeline_results, output_path):
    """Generate a validation report comparing pipeline output to ground truth."""
    report = []
    report.append("# Grounding Validation Report")
    report.append(f"\n## Video: {os.path.basename(video_path)}")
    report.append(f"\n### Video Properties")
    report.append(f"- Duration: {probe_info['duration_sec']}s")
    report.append(f"- Resolution: {probe_info['resolution']}")
    report.append(f"- Codec: {probe_info['codec']}")
    report.append(f"- File size: {probe_info['file_size_bytes']:,} bytes")
    
    if pipeline_results:
        results = pipeline_results if isinstance(pipeline_results, list) else [pipeline_results]
        for r in results:
            report.append(f"\n### Pipeline Output")
            report.append(f"- Grounding branch: {r.get('grounding_branch', '?')}")
            report.append(f"- Confidence: {r.get('confidence', '?')}")
            report.append(f"\n#### Factual Description")
            report.append(f"> {r.get('factual_description_preview', '(empty)')}")
            
            report.append(f"\n#### Captions")
            for style in ["formal", "sarcastic", "humorous_tech", "humorous_non_tech"]:
                rec = " ⭐" if r.get("recommended_style") == style else ""
                report.append(f"- **{style}**{rec}: {r.get(style, '(missing)')}")
            
            verification = r.get("verification", {})
            if verification:
                report.append(f"\n#### Verification Results")
                confirmed = verification.get("confirmed", [])
                unconfirmed = verification.get("unconfirmed", [])
                report.append(f"- Confirmed facts: {len(confirmed)}")
                for fact in confirmed:
                    report.append(f"  - ✅ {fact}")
                report.append(f"- Unconfirmed facts: {len(unconfirmed)}")
                for fact in unconfirmed:
                    report.append(f"  - ❌ {fact}")
                
                per_caption = verification.get("per_caption_issues", {})
                issues_found = any(v for v in per_caption.values())
                if issues_found:
                    report.append(f"\n#### Per-Caption Issues")
                    for style, issues in per_caption.items():
                        if issues:
                            report.append(f"- **{style}**: {issues}")
            
            timings = r.get("timings", {})
            if timings:
                report.append(f"\n#### Timings")
                for k, v in timings.items():
                    report.append(f"- {k}: {v}s")
    
    report_text = "\n".join(report)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\nReport written to: {output_path}")
    return report_text


def main():
    parser = argparse.ArgumentParser(description="Validate FourVoice Captioner grounding accuracy")
    parser.add_argument("video", help="Path to video file")
    parser.add_argument("--output-dir", default="./validation_output", help="Output directory for frames and report")
    parser.add_argument("--interval", type=float, default=2.0, help="Frame extraction interval in seconds")
    parser.add_argument("--skip-pipeline", action="store_true", help="Skip pipeline run, only extract frames")
    args = parser.parse_args()
    
    video_path = os.path.abspath(args.video)
    if not os.path.exists(video_path):
        print(f"Error: Video not found: {video_path}")
        sys.exit(1)
    
    output_dir = os.path.abspath(args.output_dir)
    frames_dir = os.path.join(output_dir, "frames")
    
    print(f"=== Validating: {os.path.basename(video_path)} ===")
    
    # Step 1: Probe and extract frames
    print("\n[1/3] Probing video and extracting frames...")
    probe_info, frame_paths, timestamps = extract_validation_frames(video_path, frames_dir, args.interval)
    print(f"  Duration: {probe_info['duration_sec']}s, Resolution: {probe_info['resolution']}")
    print(f"  Extracted {len(frame_paths)} frames at {args.interval}s intervals")
    
    # Step 2: Run pipeline
    pipeline_results = None
    if not args.skip_pipeline:
        print("\n[2/3] Running pipeline...")
        pipeline_results = run_pipeline(video_path)
        if pipeline_results:
            print("  Pipeline completed successfully")
        else:
            print("  Pipeline failed!")
    
    # Step 3: Generate report
    print("\n[3/3] Generating report...")
    report_path = os.path.join(output_dir, "validation_report.md")
    report = generate_report(video_path, probe_info, pipeline_results, report_path)
    print(report)


if __name__ == "__main__":
    main()
