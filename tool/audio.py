"""Reading audio from the class recording and transcribing it locally.

Sized for an 8 GB Apple Silicon laptop: Whisper small.en in int8 (well under
1 GB of memory), 4 CPU threads, one short window at a time.
"""
from __future__ import annotations

SR = 16000          # Whisper's sample rate
MODEL = "small.en"  # ~0.5 GB download
THREADS = 4         # half of an M1's cores, so the computer stays usable


class Recording:
    """The class video opened once over HTTP; window() reads one stretch of audio."""

    def __init__(self, url: str):
        import av
        self.av = av
        self.c = av.open(url, options={"rw_timeout": "30000000"})
        self.s = self.c.streams.audio[0]
        self.tb = self.s.time_base
        self.base = (self.c.start_time or 0) / 1_000_000

    def window(self, start: float, end: float):
        import numpy as np
        start = max(0.0, start)
        self.c.seek(int((start + self.base) / self.tb), stream=self.s, backward=True)
        res = self.av.AudioResampler(format="s16", layout="mono", rate=SR)
        chunks, first = [], None
        for frame in self.c.decode(self.s):
            if frame.pts is None:
                continue
            ft = float(frame.pts * self.tb) - self.base
            if ft + frame.samples / frame.sample_rate <= start:
                continue
            if ft >= end:
                break
            if first is None:
                first = ft
            chunks += [f.to_ndarray().reshape(-1) for f in res.resample(frame)]
        chunks += [f.to_ndarray().reshape(-1) for f in res.resample(None)]
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        a = np.concatenate(chunks).astype(np.float32) / 32768.0
        skip = max(0, int(round((start - first) * SR)))
        return a[skip: skip + int(round((end - start) * SR))]

    def close(self):
        self.c.close()


class Whisper:
    def __init__(self):
        from faster_whisper import WhisperModel
        try:
            self.m = WhisperModel(MODEL, device="cpu", compute_type="int8", cpu_threads=THREADS, num_workers=1)
        except ValueError:  # int8 not supported on this CPU build
            self.m = WhisperModel(MODEL, device="cpu", compute_type="float32", cpu_threads=THREADS, num_workers=1)

    def words(self, audio, hint: str):
        segs, _ = self.m.transcribe(audio, language="en", word_timestamps=True, vad_filter=True,
                                    initial_prompt=hint or None, condition_on_previous_text=False)
        return [(w.start, w.end, w.word) for s in segs for w in (s.words or [])]
