#!/bin/env python

import argparse
import json
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

DEFAULT_VIDEOS = [
    ('pMFH1buJOKA', 'Wayward Radio Ep. #3'),
    ('-rs7LHtODh4', 'Half-Life 3 - Rise, Fall & Rebirth'),
    ('IGLGi5RK8V8', 'Julian LeFay interview'),
    ('u7JFmo-vaXo', 'Check Out: Chains of Freedom'),
    ('vnOrkLQAU7E', 'Chains of Freedom Part 19'),
    ('OkoHyOhHEuk', 'TDS Earth Day / Climate'),
    ('LPBI7WVD0zI', 'Democracy Now headlines 2025-04-21'),
    ('Dnk3uwc-2qI', 'Tesla Bot Gen 3'),
]

EFFORT_TIERS = ['minimal', 'low', 'medium', 'high', 'xhigh']


def resolve_effort(base, override):
    if override is None:
        return base
    if override == '+1':
        if base in EFFORT_TIERS:
            i = EFFORT_TIERS.index(base)
            return EFFORT_TIERS[min(i + 1, len(EFFORT_TIERS) - 1)]
        return base
    return override


def make_usage_callback():
    from langchain_core.callbacks import BaseCallbackHandler

    class UsageCallback(BaseCallbackHandler):
        def __init__(self):
            super().__init__()
            self.input_tokens = 0
            self.output_tokens = 0

        def on_llm_end(self, response, **kwargs):
            llm_output = getattr(response, 'llm_output', None) or {}
            usage = llm_output.get('token_usage') or {}
            if usage:
                self.input_tokens += int(usage.get('prompt_tokens') or 0)
                self.output_tokens += int(usage.get('completion_tokens') or 0)
                return
            for gen_list in getattr(response, 'generations', None) or []:
                for gen in gen_list:
                    msg = getattr(gen, 'message', None)
                    if msg is None:
                        continue
                    um = getattr(msg, 'usage_metadata', None) or {}
                    self.input_tokens += int(um.get('input_tokens') or 0)
                    self.output_tokens += int(um.get('output_tokens') or 0)

    return UsageCallback()


@contextmanager
def force_model(model_id, effort_override=None):
    from analysis.processor import Processor
    from config import LLM_PROFILES
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    original = Processor.__dict__['ask_llm']
    usage_acc = []

    def wrapper(cls, prompt, params=None, *, profile, **overrides):
        base = LLM_PROFILES[profile]
        effort = resolve_effort(
            overrides.get('reasoning_effort', base.get('reasoning_effort')),
            effort_override,
        )
        kwargs = {**base, **overrides, 'model': model_id}
        if effort is not None:
            kwargs['reasoning_effort'] = effort
        else:
            kwargs.pop('reasoning_effort', None)

        cb = make_usage_callback()
        kwargs['callbacks'] = [cb]

        llm = ChatOpenAI(**kwargs)
        prompt_template = ChatPromptTemplate.from_template(prompt)
        chain = prompt_template | llm | StrOutputParser()
        text = chain.invoke(params)
        usage_acc.append({
            'input_tokens': cb.input_tokens,
            'output_tokens': cb.output_tokens,
        })
        return text

    Processor.ask_llm = classmethod(wrapper)
    try:
        yield usage_acc
    finally:
        Processor.ask_llm = original


@contextmanager
def isolated_video_dir():
    """
    Redirect `Video.get_active_dir` to a throwaway tmpdir so every file the
    formatter writes (processed/*, transcript-meta.json, etc.) lives in
    isolation and cannot corrupt production data.
    """
    from youtube import Video

    original = Video.__dict__['get_active_dir']
    tmpdir = Path(tempfile.mkdtemp(prefix='compare_models_'))

    def fake(cls, video_id):
        d = tmpdir / video_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    Video.get_active_dir = classmethod(fake)
    try:
        yield tmpdir
    finally:
        Video.get_active_dir = original
        shutil.rmtree(tmpdir, ignore_errors=True)


@contextmanager
def fake_description_timestamps(data):
    from analysis import YTAPIVideoExtractor

    original = YTAPIVideoExtractor.__dict__['get_description_timestamps']

    def fake(cls, video):
        return data

    YTAPIVideoExtractor.get_description_timestamps = classmethod(fake)
    try:
        yield
    finally:
        YTAPIVideoExtractor.get_description_timestamps = original


def sum_usage(usage_acc):
    return {
        'in_tok': sum(u['input_tokens'] for u in usage_acc),
        'out_tok': sum(u['output_tokens'] for u in usage_acc),
    }


def run_chunk_combo(video, transcript, model, effort_override):
    from analysis import YTTranscriptFormatter
    with isolated_video_dir():
        with force_model(model, effort_override) as usage_acc:
            t0 = time.monotonic()
            text = YTTranscriptFormatter.run_chunk(video, transcript, 0)
            elapsed = time.monotonic() - t0
    return text, {'seconds': round(elapsed, 2), **sum_usage(usage_acc)}


def run_headings_combo(video, transcript_text, description_timestamps, model, effort_override):
    from analysis import YTTranscriptFormatter
    with isolated_video_dir():
        with fake_description_timestamps(description_timestamps):
            with force_model(model, effort_override) as usage_acc:
                t0 = time.monotonic()
                text = YTTranscriptFormatter.run_cleanup_headings(video, transcript_text)
                elapsed = time.monotonic() - t0
    return text, {'seconds': round(elapsed, 2), **sum_usage(usage_acc)}


def run_extractor_combo(video, model, effort_override):
    from analysis import YTAPIVideoExtractor
    with isolated_video_dir():
        with force_model(model, effort_override) as usage_acc:
            t0 = time.monotonic()
            result = YTAPIVideoExtractor.run(video)
            elapsed = time.monotonic() - t0
    return result, {'seconds': round(elapsed, 2), **sum_usage(usage_acc)}


def read_production_transcript(video_id):
    """
    Full cleaned transcript text to feed into the headings benchmark.

    Post-normalization, the cleaned transcript lives in `transcript.txt`
    directly. A legacy `transcript_cleaned.txt` is accepted as a fallback
    for videos that have not yet been run through the new migration.
    """
    from youtube import Video
    processed = Video.get_processed_dir(video_id)
    transcript = processed / 'transcript.txt'
    if transcript.exists():
        text = transcript.read_text()
        # If the file still carries the old v1 assembled format with
        # `##` heading lines interleaved, strip them so the benchmark
        # sees a heading-free input.
        return '\n'.join(
            line for line in text.split('\n')
            if not line.lstrip().startswith('##')
        )
    cleaned = processed / 'transcript_cleaned.txt'
    if cleaned.exists():
        return cleaned.read_text()
    return None


def build_chunk_combos(extra_effort):
    """Cleanup sweep — run_chunk on its own, no heading generation.

    Note: `gpt-5.4-mini` does not support `reasoning_effort='minimal'` (API
    returns 400). `none` is supported but produced below-spec filler
    removal on pMFH1buJOKA (kept 4× as many 'uh'/'you know' as medium), so
    it is not worth sweeping across all videos.
    """
    combos = [
        ('5.4-mini-medium', 'gpt-5.4-mini', 'medium'),
        ('5.4-mini-low',    'gpt-5.4-mini', 'low'),
        ('5.4-nano-medium', 'gpt-5.4-nano', 'medium'),
        ('5.4-nano-low',    'gpt-5.4-nano', 'low'),
    ]
    if extra_effort:
        combos.append((f'5.4-mini-{extra_effort}', 'gpt-5.4-mini', extra_effort))
    return combos


def build_headings_combos(extra_effort):
    """Headings sweep — full-transcript creative pass, different cost profile.

    `gpt-5-mini` as a reference was dropped after it hung on a long transcript
    (HL3) on an accidental run. The cleanup sweep already confirmed the 5.4
    family is strictly faster; we don't need the reference for the pick.
    """
    combos = [
        ('5.4-mini-medium', 'gpt-5.4-mini', 'medium'),
        ('5.4-mini-high',   'gpt-5.4-mini', 'high'),
        ('5.4-nano-medium', 'gpt-5.4-nano', 'medium'),
        ('5.4-nano-high',   'gpt-5.4-nano', 'high'),
    ]
    if extra_effort:
        combos.append((f'5.4-mini-{extra_effort}', 'gpt-5.4-mini', extra_effort))
    return combos


def build_extractor_combos(extra_effort):
    """Extractor combos — orthogonal to the two-phase split; kept from the prior run."""
    combos = [
        ('mini', 'gpt-5-mini', None),
        ('5.4-mini', 'gpt-5.4-mini', None),
        ('nano-same', 'gpt-5.4-nano', None),
        ('nano-bump', 'gpt-5.4-nano', '+1'),
    ]
    if extra_effort:
        combos.append((f'nano-{extra_effort}', 'gpt-5.4-nano', extra_effort))
    return combos


def render_summary(results):
    lines = ['# Model comparison', '']
    for video_id, description, timing in results:
        heading = f'[{video_id}]({video_id}/)'
        if description:
            heading += f' — {description}'
        lines.append(f'## {heading}')
        lines.append('')
        for component in ('chunk0', 'headings', 'extractor'):
            label_timings = timing.get(component)
            if not label_timings:
                continue
            lines.append(f'### {component}')
            lines.append('')
            if component == 'extractor':
                lines.append('| label | model | seconds | in_tok | out_tok | verdict | coverage |')
                lines.append('|---|---|---|---|---|---|---|')
            else:
                lines.append('| label | model | seconds | in_tok | out_tok |')
                lines.append('|---|---|---|---|---|')
            for label, info in label_timings.items():
                if 'error' in info:
                    error = info['error']
                    if component == 'extractor':
                        lines.append(f"| {label} | {info['model']} | ERROR: {error} | — | — | — | — |")
                    else:
                        lines.append(f"| {label} | {info['model']} | ERROR: {error} | — | — |")
                    continue
                row = (
                    f"| {label} | {info['model']} | {info['seconds']} "
                    f"| {info['in_tok']} | {info['out_tok']}"
                )
                if component == 'extractor':
                    row += f" | {info.get('verdict', '—')} | {info.get('coverage', '—')}"
                row += ' |'
                lines.append(row)
            lines.append('')
    return '\n'.join(lines) + '\n'


def load_existing_timing(out_dir):
    timing_file = out_dir / 'timing.json'
    if timing_file.exists():
        return json.loads(timing_file.read_text())
    return {}


def process_video(
    video_id,
    description,
    chunk_combos,
    headings_combos,
    extractor_combos,
    output_root,
    skip_existing,
):
    from analysis import YTAPIVideoExtractor
    from youtube import Video

    print(f'\n=== {video_id} {description} ===')
    video = Video.get(video_id)

    out_dir = output_root / video_id
    out_dir.mkdir(parents=True, exist_ok=True)

    timing = load_existing_timing(out_dir)

    transcript = video.transcript()
    if transcript is None:
        print(f'  [skip chunk0] no transcript for {video_id}')
    else:
        timing.setdefault('chunk0', {})
        for label, model, override in chunk_combos:
            out_file = out_dir / f'chunk0__{label}.txt'
            if skip_existing and out_file.exists() and label in timing['chunk0']:
                print(f'  chunk0 / {label} [cached]')
                continue
            print(f'  chunk0 / {label} ({model})')
            try:
                text, stats = run_chunk_combo(video, transcript, model, override)
                out_file.write_text(text)
                timing['chunk0'][label] = {'model': model, **stats}
            except Exception as e:
                print(f'    [error] {e}')
                timing['chunk0'][label] = {'model': model, 'error': str(e)}

    transcript_text = read_production_transcript(video_id)
    if transcript_text is None:
        print(f'  [skip headings] no cleaned transcript for {video_id}')
    else:
        description_timestamps = None
        timing.setdefault('headings', {})
        for label, model, override in headings_combos:
            out_file = out_dir / f'headings__{label}.txt'
            if skip_existing and out_file.exists() and label in timing['headings']:
                print(f'  headings / {label} [cached]')
                continue
            if description_timestamps is None:
                print('  preparing description timestamps (one-time lookup)')
                description_timestamps = YTAPIVideoExtractor.get_description_timestamps(video)
            print(f'  headings / {label} ({model})')
            try:
                text, stats = run_headings_combo(
                    video, transcript_text, description_timestamps, model, override
                )
                out_file.write_text(text)
                timing['headings'][label] = {'model': model, **stats}
            except Exception as e:
                print(f'    [error] {e}')
                timing['headings'][label] = {'model': model, 'error': str(e)}

    timing.setdefault('extractor', {})
    for label, model, override in extractor_combos:
        out_file = out_dir / f'extractor__{label}.json'
        if skip_existing and out_file.exists() and label in timing['extractor']:
            print(f'  extractor / {label} [cached]')
            continue
        print(f'  extractor / {label} ({model})')
        try:
            result, stats = run_extractor_combo(video, model, override)
            out_file.write_text(json.dumps(result, indent=2, default=str))
            timing['extractor'][label] = {
                'model': model,
                'verdict': result.get('evaluation', {}).get('verdict'),
                'coverage': result.get('evaluation', {}).get('coverage'),
                **stats,
            }
        except Exception as e:
            print(f'    [error] {e}')
            timing['extractor'][label] = {'model': model, 'error': str(e)}

    (out_dir / 'timing.json').write_text(json.dumps(timing, indent=2))
    return timing


def main():
    parser = argparse.ArgumentParser(
        description='Benchmark the two-phase transcript formatter across models and effort tiers.'
    )
    parser.add_argument('videos', nargs='*', help='Video IDs (default: built-in list)')
    parser.add_argument('--extra-effort', help='Add an extra combo pinned at this effort level')
    parser.add_argument('--limit', type=int, default=None, help='Process at most N videos')
    parser.add_argument('--skip-existing', action='store_true',
                        help='Skip combos whose output files already exist')
    parser.add_argument('--skip-chunk', action='store_true',
                        help='Skip the cleanup (run_chunk) sweep')
    parser.add_argument('--skip-headings', action='store_true',
                        help='Skip the headings (run_cleanup_headings) sweep')
    parser.add_argument('--skip-extractor', action='store_true',
                        help='Skip the extractor sweep')
    args = parser.parse_args()

    if args.videos:
        videos = [(vid, '') for vid in args.videos]
    else:
        videos = DEFAULT_VIDEOS
    if args.limit:
        videos = videos[:args.limit]

    chunk_combos = [] if args.skip_chunk else build_chunk_combos(args.extra_effort)
    headings_combos = [] if args.skip_headings else build_headings_combos(args.extra_effort)
    extractor_combos = [] if args.skip_extractor else build_extractor_combos(args.extra_effort)
    output_root = Path('var/model_comparison')
    output_root.mkdir(parents=True, exist_ok=True)

    results = []
    for video_id, description in videos:
        try:
            timing = process_video(
                video_id,
                description,
                chunk_combos,
                headings_combos,
                extractor_combos,
                output_root,
                args.skip_existing,
            )
            results.append((video_id, description, timing))
        except Exception as e:
            print(f'[error] {video_id}: {e}')

    (output_root / 'SUMMARY.md').write_text(render_summary(results))
    print(f'\nWrote {output_root}/SUMMARY.md')


if __name__ == '__main__':
    main()
