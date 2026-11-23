"""Persistent, local-only Whisper worker; stdout carries JSON protocol exclusively."""
import json
import sys
import time
import wave
import numpy as np


def main():
    from faster_whisper import WhisperModel
    model = WhisperModel(sys.argv[1], device="cpu", compute_type="int8", cpu_threads=2,
                         num_workers=1, local_files_only=True)
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            started = time.perf_counter()
            with wave.open(request["path"], "rb") as stream:
                rate = stream.getframerate()
                channels = stream.getnchannels()
                if stream.getsampwidth() != 2:
                    raise ValueError("A captura precisa estar em PCM16")
                audio = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").astype(np.float32) / 32768
                audio = audio.reshape(-1, channels).mean(axis=1)
            if rate != 16000:
                target = max(1, round(len(audio) * 16000 / rate))
                audio = np.interp(np.arange(target) * rate / 16000, np.arange(len(audio)), audio).astype(np.float32)
            segments, _ = model.transcribe(audio, language="pt", beam_size=1,
                                            best_of=1, temperature=0, vad_filter=False,
                                            condition_on_previous_text=False)
            text = " ".join(segment.text.strip() for segment in segments).strip()
            print(json.dumps({"text": text, "elapsed": time.perf_counter() - started}, ensure_ascii=False), flush=True)
        except Exception as error:
            print(json.dumps({"error": str(error)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
