"""
AI Viral Stream Clipper Engine — parses transcripts, chunks multi-hour streams,
queries Gemini/OpenAI/Ollama APIs, and snaps timestamps to sentence boundaries.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

from core.online_trimmer import format_seconds, parse_timestamp_str
from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class SubtitleBlock:
    """A single parsed subtitle cue from an SRT/VTT file."""

    index: int
    start_sec: float
    end_sec: float
    text: str
    is_sentence_end: bool = False


@dataclass
class ViralClip:
    """An AI-detected or user-refined viral highlight moment."""

    id: str
    rank: int
    title: str
    viral_score: int
    reason: str
    start_sec: float
    end_sec: float
    hook_quote: str = ""
    included: bool = True

    @property
    def duration_sec(self) -> float:
        return max(0.5, self.end_sec - self.start_sec)

    @property
    def time_range_str(self) -> str:
        return f"{format_seconds(self.start_sec)} → {format_seconds(self.end_sec)}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["duration_sec"] = self.duration_sec
        d["time_range_str"] = self.time_range_str
        return d


def parse_srt_content(raw_text: str) -> list[SubtitleBlock]:
    """
    Parse raw SRT or VTT content into a list of SubtitleBlock instances
    with detected sentence boundaries.
    """
    if not raw_text or not raw_text.strip():
        return []

    # Normalize line breaks and remove VTT headers
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"^WEBVTT.*?\n\n", "", text, flags=re.DOTALL | re.IGNORECASE)

    # Split into cue blocks by blank lines
    blocks_raw = re.split(r"\n\s*\n", text.strip())
    parsed_blocks: list[SubtitleBlock] = []

    time_pattern = re.compile(
        r"(\d{1,2}:)?(\d{1,2}):(\d{1,2})[,\.](\d{1,3})\s*-->\s*(\d{1,2}:)?(\d{1,2}):(\d{1,2})[,\.](\d{1,3})"
    )

    def _to_sec(h_str, m_str, s_str, ms_str) -> float:
        h = float(h_str.rstrip(":")) if h_str else 0.0
        m = float(m_str) if m_str else 0.0
        s = float(s_str) if s_str else 0.0
        ms = float(ms_str.ljust(3, "0")[:3]) / 1000.0 if ms_str else 0.0
        return h * 3600.0 + m * 60.0 + s + ms

    idx_counter = 1
    for block_str in blocks_raw:
        lines = [line.strip() for line in block_str.split("\n") if line.strip()]
        if not lines:
            continue

        match = None
        text_lines = []
        for line in lines:
            m = time_pattern.search(line)
            if m:
                match = m
            elif not re.match(r"^\d+$", line):  # Skip pure index lines
                # Strip HTML / formatting tags like <font>, <b>, <c>
                clean = re.sub(r"<[^>]+>", "", line).strip()
                if clean:
                    text_lines.append(clean)

        if match and text_lines:
            g = match.groups()
            s_time = _to_sec(g[0], g[1], g[2], g[3])
            e_time = _to_sec(g[4], g[5], g[6], g[7])
            joined_text = " ".join(text_lines)

            # Check if this block marks a natural sentence end
            # e.g. ends with ., !, ?, ؟ or quotes
            is_end = bool(re.search(r"[\.!\?؟][\"'»]?\s*$", joined_text))

            parsed_blocks.append(
                SubtitleBlock(
                    index=idx_counter,
                    start_sec=s_time,
                    end_sec=max(s_time + 0.2, e_time),
                    text=joined_text,
                    is_sentence_end=is_end,
                )
            )
            idx_counter += 1

    # Second pass: mark natural pauses (gap >= 0.8s to next block) as sentence ends
    for i in range(len(parsed_blocks) - 1):
        gap = parsed_blocks[i + 1].start_sec - parsed_blocks[i].end_sec
        if gap >= 0.8:
            parsed_blocks[i].is_sentence_end = True

    if parsed_blocks:
        parsed_blocks[-1].is_sentence_end = True

    return parsed_blocks


def fetch_stream_subtitles(url: str, preferred_langs: tuple = ("en", "ar", "fr", "es")) -> Optional[str]:
    """
    Fetch existing subtitles or auto-captions from a YouTube/stream URL via yt-dlp
    in ~2 seconds without downloading any video media.
    """
    import yt_dlp

    with tempfile.TemporaryDirectory(prefix="audiomorph_subs_") as tmp_dir:
        out_tpl = os.path.join(tmp_dir, "stream_sub.%(ext)s")
        ydl_opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": list(preferred_langs),
            "subtitlesformat": "srt/vtt/best",
            "outtmpl": out_tpl,
            "quiet": True,
            "no_warnings": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # Find generated subtitle file
            files = [os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir) if f.endswith((".srt", ".vtt"))]
            if files:
                # Prefer .srt if available
                files.sort(key=lambda x: (0 if x.endswith(".srt") else 1))
                with open(files[0], "r", encoding="utf-8", errors="replace") as fh:
                    return fh.read()
        except Exception as exc:
            log.warning("fetch_stream_subtitles failed for %s: %s", url, exc)

    return None


def chunk_subtitles(
    blocks: list[SubtitleBlock],
    chunk_duration_sec: float = 900.0,  # 15 minutes
    overlap_sec: float = 90.0,          # 1.5 minutes
) -> list[list[SubtitleBlock]]:
    """
    Divide multi-hour stream subtitle blocks into overlapping chunks so API
    context windows are respected while preserving cross-boundary context.
    """
    if not blocks:
        return []

    total_duration = blocks[-1].end_sec - blocks[0].start_sec
    if total_duration <= chunk_duration_sec + 60.0:
        return [blocks]

    chunks: list[list[SubtitleBlock]] = []
    current_start = blocks[0].start_sec

    while current_start < blocks[-1].end_sec:
        current_end = current_start + chunk_duration_sec
        chunk = [b for b in blocks if (b.end_sec >= current_start and b.start_sec <= current_end)]
        if chunk:
            chunks.append(chunk)
        current_start += (chunk_duration_sec - overlap_sec)

    return chunks


def build_chunk_prompt_text(chunk: list[SubtitleBlock]) -> str:
    """Format subtitle blocks with timestamp markers for AI analysis."""
    lines = []
    for b in chunk:
        time_tag = format_seconds(b.start_sec)
        lines.append(f"[{time_tag}] {b.text}")
    return "\n".join(lines)


def query_gemini_api(
    prompt: str,
    api_key: str,
    model: str = "gemini-2.5-flash",
    timeout: int = 40,
) -> str:
    """Call Google Gemini API using Python standard library urllib.request."""
    if not api_key or not api_key.strip():
        raise ValueError("Missing Gemini API Key. Please enter your API key in AI Settings.")

    clean_model = model.strip() or "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key.strip()}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.35,
            "responseMimeType": "application/json",
        },
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read().decode("utf-8")
            data = json.loads(resp_body)
            candidates = data.get("candidates") or []
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return ""
    except urllib.error.HTTPError as http_err:
        err_msg = http_err.read().decode("utf-8", errors="replace")
        log.error("Gemini API HTTP Error %d: %s", http_err.code, err_msg)
        raise RuntimeError(f"Gemini API Error ({http_err.code}): {err_msg}") from http_err
    except Exception as exc:
        log.error("Gemini API connection error: %s", exc)
        raise RuntimeError(f"Failed to connect to Gemini API: {exc}") from exc


def query_openai_or_ollama(
    prompt: str,
    api_key: str,
    endpoint: str = "http://localhost:11434/v1/chat/completions",
    model: str = "gpt-4o-mini",
    timeout: int = 40,
) -> str:
    """Call an OpenAI-compatible endpoint or local Ollama server using urllib.request."""
    url = endpoint.strip() or "http://localhost:11434/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key and api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    payload = {
        "model": model.strip() or "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a top-tier viral video director for TikTok, YouTube Shorts, and Reels. "
                    "Analyze transcript chunks and return only valid JSON matching the requested schema."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.35,
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read().decode("utf-8")
            data = json.loads(resp_body)
            choices = data.get("choices") or []
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return ""
    except urllib.error.HTTPError as http_err:
        err_msg = http_err.read().decode("utf-8", errors="replace")
        log.error("OpenAI/Ollama HTTP Error %d: %s", http_err.code, err_msg)
        raise RuntimeError(f"AI Provider Error ({http_err.code}): {err_msg}") from http_err
    except Exception as exc:
        log.error("OpenAI/Ollama connection error: %s", exc)
        raise RuntimeError(f"Failed to connect to AI endpoint: {exc}") from exc


def fallback_heuristic_highlights(
    blocks: list[SubtitleBlock],
    target_count: int = 5,
    min_dur: float = 20.0,
    max_dur: float = 60.0,
    focus_keywords: str = "",
) -> list[dict[str, Any]]:
    """
    Offline heuristic highlight scanner that finds high-energy moments when
    no AI API key is configured or offline.
    """
    if not blocks:
        return []

    user_kw = [k.strip().lower() for k in re.split(r"[\s,]+", focus_keywords) if k.strip()]
    candidates: list[dict[str, Any]] = []

    # Slide a window across subtitle blocks
    window_start_idx = 0
    total_blocks = len(blocks)

    while window_start_idx < total_blocks:
        start_b = blocks[window_start_idx]
        acc_text: list[str] = [start_b.text]
        end_idx = window_start_idx

        # Accumulate blocks until min_dur is reached
        while end_idx + 1 < total_blocks:
            next_b = blocks[end_idx + 1]
            dur = next_b.end_sec - start_b.start_sec
            if dur > max_dur:
                break
            end_idx += 1
            acc_text.append(next_b.text)
            if dur >= min_dur and next_b.is_sentence_end:
                break

        curr_dur = blocks[end_idx].end_sec - start_b.start_sec
        if curr_dur >= min_dur:
            full_txt = " ".join(acc_text)
            score = 65

            # Energy score boosts
            score += min(15, full_txt.count("!") * 4)
            score += min(10, full_txt.count("?") * 3)
            if re.search(r"\b(crazy|insane|secret|never|mistake|funny|omg|wow|truth|win|fail)\b", full_txt, re.I):
                score += 8
            if user_kw:
                for kw in user_kw:
                    if kw in full_txt.lower():
                        score += 10

            score = min(98, score)
            first_sentence = full_txt.split(".")[0][:60]
            candidates.append({
                "title": f"Highlight: {first_sentence}...",
                "viral_score": score,
                "reason": "High speech density and punchy dialogue delivery",
                "start_time": format_seconds(start_b.start_sec),
                "end_time": format_seconds(blocks[end_idx].end_sec),
                "quote": full_txt[:120],
            })

        # Advance window by ~45 seconds
        target_adv_sec = start_b.start_sec + 40.0
        while window_start_idx < total_blocks and blocks[window_start_idx].start_sec < target_adv_sec:
            window_start_idx += 1

    candidates.sort(key=lambda x: x["viral_score"], reverse=True)
    return candidates[:target_count]


def snap_clip_boundaries(
    raw_clips: list[dict[str, Any]],
    blocks: list[SubtitleBlock],
    min_dur: float = 15.0,
    max_dur: float = 75.0,
    sentence_guard: bool = True,
    target_count: int = 5,
) -> list[ViralClip]:
    """
    Refine AI-proposed clip timestamps by snapping to exact opening subtitle lines
    and completing incomplete sentences with outro padding. Deduplicates overlaps.
    """
    if not raw_clips or not blocks:
        return []

    snapped_clips: list[ViralClip] = []

    for i, item in enumerate(raw_clips):
        raw_start = parse_timestamp_str(str(item.get("start_time", 0)))
        raw_end = parse_timestamp_str(str(item.get("end_time", raw_start + 30)))

        if raw_end <= raw_start:
            raw_end = raw_start + 30.0

        # 1. Snap start time to closest opening block
        start_idx = 0
        min_start_diff = float("inf")
        for b_idx, b in enumerate(blocks):
            diff = abs(b.start_sec - raw_start)
            if diff < min_start_diff:
                min_start_diff = diff
                start_idx = b_idx

        # 0.25s breathing room before speech
        snapped_start = max(0.0, blocks[start_idx].start_sec - 0.25)

        # 2. Snap end time to a complete sentence
        end_idx = start_idx
        for b_idx in range(start_idx, len(blocks)):
            if blocks[b_idx].end_sec >= raw_end:
                end_idx = b_idx
                break

        if sentence_guard:
            # Advance to next sentence completion if current block is mid-sentence
            while end_idx < len(blocks) - 1 and not blocks[end_idx].is_sentence_end:
                # But don't exceed max_dur + 10s grace
                if blocks[end_idx].end_sec - snapped_start > max_dur + 10.0:
                    break
                end_idx += 1

        # 0.35s outro buffer after speaker finishes thought
        snapped_end = blocks[end_idx].end_sec + 0.35

        # Enforce bounds
        dur = snapped_end - snapped_start
        if dur < min_dur:
            snapped_end = min(blocks[-1].end_sec, snapped_start + min_dur)
        elif dur > max_dur + 15.0:
            snapped_end = snapped_start + max_dur

        title = str(item.get("title") or f"Viral Clip #{i+1}").strip()
        score = int(item.get("viral_score") or 80)
        reason = str(item.get("reason") or "Engaging social hook").strip()
        quote = str(item.get("quote") or "").strip()

        snapped_clips.append(
            ViralClip(
                id=f"clip_{i+1}",
                rank=i + 1,
                title=title,
                viral_score=score,
                reason=reason,
                start_sec=round(snapped_start, 2),
                end_sec=round(snapped_end, 2),
                hook_quote=quote,
                included=True,
            )
        )

    # 3. Deduplicate overlapping clips (if overlap > 50% keep higher viral_score)
    snapped_clips.sort(key=lambda c: c.viral_score, reverse=True)
    filtered_clips: list[ViralClip] = []

    for c in snapped_clips:
        has_overlap = False
        for kept in filtered_clips:
            ov_start = max(c.start_sec, kept.start_sec)
            ov_end = min(c.end_sec, kept.end_sec)
            if ov_end > ov_start:
                ov_dur = ov_end - ov_start
                if ov_dur / min(c.duration_sec, kept.duration_sec) >= 0.50:
                    has_overlap = True
                    break
        if not has_overlap:
            filtered_clips.append(c)

    # Re-rank and limit to target_count
    final_clips = filtered_clips[:target_count]
    for r_idx, fc in enumerate(final_clips):
        fc.rank = r_idx + 1

    return final_clips


def analyze_stream_for_viral_clips(
    blocks: list[SubtitleBlock],
    settings: dict,
    focus_instructions: str = "",
    target_count: int = 5,
    duration_preset: str = "Reel/TikTok (30–60s)",
    sentence_guard: bool = True,
    progress_callback: Optional[Callable[[str, float], None]] = None,
) -> list[ViralClip]:
    """
    Main entry point: analyzes a stream transcript using the configured AI engine,
    handles chunking, enforces constraints, and returns sorted ViralClip instances.
    """
    if not blocks:
        return []

    # Map duration preset to (min_sec, max_sec)
    dur_map = {
        "Short (15–30s)": (15.0, 30.0),
        "Reel/TikTok (30–60s)": (30.0, 60.0),
        "Long Story (60–90s)": (60.0, 90.0),
        "Custom": (15.0, 90.0),
    }
    min_dur, max_dur = dur_map.get(duration_preset, (30.0, 60.0))

    provider = settings.get("ai_provider", "Google Gemini API (Recommended)")
    api_key = (settings.get("ai_api_key") or "").strip()
    model = (settings.get("ai_model") or "gemini-2.5-flash").strip()
    endpoint = (settings.get("ai_custom_endpoint") or "http://localhost:11434/v1/chat/completions").strip()

    # If no API key is provided and using Gemini, run the heuristic fallback
    if "gemini" in provider.lower() and not api_key:
        if progress_callback:
            progress_callback("Running heuristic highlight detector (Add API key in settings for deep AI)...", 0.5)
        raw_heuristics = fallback_heuristic_highlights(
            blocks,
            target_count=target_count,
            min_dur=min_dur,
            max_dur=max_dur,
            focus_keywords=focus_instructions,
        )
        return snap_clip_boundaries(
            raw_heuristics, blocks, min_dur, max_dur, sentence_guard, target_count
        )

    # Split into manageable chunks
    chunks = chunk_subtitles(blocks, chunk_duration_sec=900.0, overlap_sec=90.0)
    total_chunks = len(chunks)
    all_raw_clips: list[dict[str, Any]] = []

    for c_idx, chunk in enumerate(chunks):
        pct = (c_idx + 1) / total_chunks
        if progress_callback:
            progress_callback(f"Analyzing stream section {c_idx+1}/{total_chunks} with AI...", pct * 0.9)

        transcript_text = build_chunk_prompt_text(chunk)
        user_focus = f"\nUser Custom Focus Instructions:\n\"{focus_instructions}\"\n" if focus_instructions else ""

        prompt = (
            "You are a master social media video editor specializing in viral YouTube Shorts, TikToks, and Instagram Reels.\n"
            f"Analyze the following stream transcript and identify the top engaging, dramatic, funny, or actionable moments.\n"
            f"{user_focus}\n"
            "Rules:\n"
            f"1. Target clip duration: between {int(min_dur)}s and {int(max_dur)}s.\n"
            "2. Each clip must have a strong opening hook and complete the speaker's sentence/thought.\n"
            "3. Assign a realistic viral_score from 1 to 100 based on hook strength, emotional impact, and shareability.\n"
            "4. Return ONLY a valid JSON array of objects with the exact schema below and NO markdown formatting:\n"
            "[\n"
            "  {\n"
            '    "title": "Punchy Hook (Max 6 words)",\n'
            '    "viral_score": 95,\n'
            '    "reason": "One-line viral breakdown",\n'
            '    "start_time": "HH:MM:SS",\n'
            '    "end_time": "HH:MM:SS",\n'
            '    "quote": "First line spoken"\n'
            "  }\n"
            "]\n\n"
            "TRANSCRIPT:\n"
            f"{transcript_text}"
        )

        try:
            if "gemini" in provider.lower():
                resp_text = query_gemini_api(prompt, api_key=api_key, model=model)
            else:
                resp_text = query_openai_or_ollama(prompt, api_key=api_key, endpoint=endpoint, model=model)

            # Clean JSON markdown fences if present
            cleaned_resp = re.sub(r"^```json\s*", "", resp_text.strip(), flags=re.IGNORECASE)
            cleaned_resp = re.sub(r"```$", "", cleaned_resp).strip()
            data = json.loads(cleaned_resp)
            if isinstance(data, list):
                all_raw_clips.extend(data)
        except Exception as exc:
            log.warning("AI chunk analysis error on chunk %d: %s", c_idx + 1, exc)

    if not all_raw_clips:
        # Fallback to heuristics if AI returned nothing
        if progress_callback:
            progress_callback("AI returned no clips — applying smart highlight fallback...", 0.95)
        all_raw_clips = fallback_heuristic_highlights(
            blocks,
            target_count=target_count,
            min_dur=min_dur,
            max_dur=max_dur,
            focus_keywords=focus_instructions,
        )

    if progress_callback:
        progress_callback("Snapping clip boundaries & sentence completion...", 1.0)

    return snap_clip_boundaries(
        all_raw_clips,
        blocks=blocks,
        min_dur=min_dur,
        max_dur=max_dur,
        sentence_guard=sentence_guard,
        target_count=target_count,
    )
