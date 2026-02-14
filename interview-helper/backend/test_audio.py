"""
Standalone audio capture test.
Records 5 seconds of system audio, saves to WAV, and sends to Whisper.
Run: python test_audio.py
"""
import numpy as np
import io
import wave
import time
import os

# Apply numpy patch BEFORE importing soundcard
if not hasattr(np, "_original_fromstring"):
    np._original_fromstring = getattr(np, "fromstring", None)
    def _patched_fromstring(string, dtype=float, count=-1, *, sep="", like=None):
        if sep == "" or sep is None:
            return np.frombuffer(string, dtype=dtype, count=count).copy()
        if np._original_fromstring is not None:
            return np._original_fromstring(string, dtype=dtype, count=count, sep=sep)
        raise TypeError("fromstring with sep requires original numpy.fromstring")
    np.fromstring = _patched_fromstring

import soundcard as sc

def record_and_test():
    print("=" * 60)
    print("AUDIO CAPTURE TEST")
    print("=" * 60)
    
    # Get speaker
    speaker = sc.default_speaker()
    print(f"Speaker: {speaker.name}")
    
    mic = sc.get_microphone(id=str(speaker.id), include_loopback=True)
    
    sample_rate = 48000
    duration = 5  # seconds
    num_frames = sample_rate * duration
    
    print(f"\n🎙  Recording {duration}s of system audio at {sample_rate}Hz...")
    print("   >>> PLAY SOMETHING WITH SPEECH NOW! <<<\n")
    
    time.sleep(1)  # Give user a moment
    
    with mic.recorder(samplerate=sample_rate, channels=2) as recorder:
        audio = recorder.record(numframes=num_frames)
    
    print(f"✅ Recorded: shape={audio.shape}, dtype={audio.dtype}")
    rms = float(np.sqrt(np.mean(audio ** 2)))
    print(f"   RMS level: {rms:.6f}")
    
    if rms < 0.001:
        print("   ⚠️  Audio is nearly SILENT! Is something playing?")
    else:
        print(f"   ✅ Audio detected (RMS={rms:.4f})")
    
    # Convert to mono 16kHz
    mono = np.mean(audio, axis=1)
    ratio = sample_rate / 16000
    num_target = int(len(mono) / ratio)
    indices = (np.arange(num_target) * ratio).astype(int)
    mono_16k = mono[indices]
    
    # Encode WAV
    audio_int16 = np.clip(mono_16k, -1.0, 1.0)
    audio_int16 = (audio_int16 * 32767).astype(np.int16)
    
    wav_buf = io.BytesIO()
    with wave.open(wav_buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio_int16.tobytes())
    wav_buf.seek(0)
    wav_bytes = wav_buf.read()
    
    # Save to file
    os.makedirs("debug_audio", exist_ok=True)
    wav_path = "debug_audio/test_5s.wav"
    with open(wav_path, "wb") as f:
        f.write(wav_bytes)
    print(f"\n💾 Saved: {wav_path} ({len(wav_bytes)} bytes)")
    
    # Try Whisper
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
        
        api_key = os.environ.get("AI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("AI_BASE_URL")
        if not api_key:
            print("\n⚠️  No AI_API_KEY/OPENAI_API_KEY found, skipping Whisper test")
            return
        
        from openai import OpenAI
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)
        
        audio_file = io.BytesIO(wav_bytes)
        audio_file.name = "test.wav"
        
        print("\n🎤 Sending to Whisper...")
        start = time.time()
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="en",
            response_format="text",
        )
        elapsed = (time.time() - start) * 1000
        
        print(f"📝 Whisper result ({elapsed:.0f}ms):")
        print(f"   \"{response}\"")
        
        if response.strip().lower() in ("you", "thank you", ""):
            print("\n❌ Whisper returned a hallucination. Audio may not contain speech.")
        else:
            print("\n✅ Real transcription! Audio capture works.")
    
    except Exception as e:
        print(f"\n❌ Whisper error: {e}")

if __name__ == "__main__":
    record_and_test()
