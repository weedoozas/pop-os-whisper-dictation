#!/usr/bin/env python3
import json
import os
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path


BASE_DIR = Path.home() / "voice-toggle"
STATE_FILE = BASE_DIR / "state.json"
RECORDING_FILE = BASE_DIR / "recording.wav"
LOCK_FILE = BASE_DIR / "toggle.lock"
PYTHON_BIN = BASE_DIR / ".venv" / "bin" / "python"
START_SOUND = "/usr/share/sounds/Pop/stereo/notification/complete.oga"
DONE_SOUND = "/usr/share/sounds/Pop/stereo/action/bell.oga"
MODEL_NAME = "medium"
PERF_LOG_FILE = BASE_DIR / "performance.log"
DEFAULT_LANGUAGE_TOOL_LANG = "es"
LANGUAGE_TOOL_LANG_MAP = {
    "en": "en-US",
    "es": "es",
}


def ensure_dirs() -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)


def run_quiet(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def play_sound(path: str) -> None:
    if Path(path).exists() and shutil.which("paplay"):
        subprocess.Popen(["paplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def notify(title: str, body: str) -> None:
    if shutil.which("notify-send"):
        subprocess.Popen(["notify-send", title, body], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def preview_text(text: str, limit: int = 120) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def capitalize_first_letter(text: str) -> str:
    for index, char in enumerate(text):
        if char.isalpha():
            return text[:index] + char.upper() + text[index + 1 :]
    return text


def read_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def write_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state))


def clear_state() -> None:
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def append_perf_log(event: dict) -> None:
    with PERF_LOG_FILE.open("a") as f:
        f.write(json.dumps(event, ensure_ascii=True) + "\n")


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start_recording() -> int:
    if RECORDING_FILE.exists():
        RECORDING_FILE.unlink()
    cmd = [
        "arecord",
        "-q",
        "-f",
        "S16_LE",
        "-c",
        "1",
        "-r",
        "16000",
        str(RECORDING_FILE),
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc.pid


def stop_recording(pid: int) -> bool:
    try:
        os.kill(pid, signal.SIGINT)
    except ProcessLookupError:
        return False

    for _ in range(40):
        if not process_alive(pid):
            return True
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    return True


def transcribe() -> tuple[str, str, float]:
    code = r'''
import json
from faster_whisper import WhisperModel

model = WhisperModel("'''+ MODEL_NAME + r'''", device="cpu", compute_type="int8")
segments, info = model.transcribe(r"'''+ str(RECORDING_FILE) + r'''", beam_size=3, vad_filter=True)
text = " ".join(segment.text.strip() for segment in segments).strip()
print(json.dumps({
    "text": text,
    "language": info.language,
    "language_probability": info.language_probability,
}))
'''
    proc = subprocess.run(
        [str(PYTHON_BIN), "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "No se pudo transcribir el audio")
    payload = json.loads(proc.stdout.strip())
    return (
        payload.get("text", "").strip(),
        payload.get("language") or DEFAULT_LANGUAGE_TOOL_LANG,
        float(payload.get("language_probability") or 0.0),
    )


def normalize_language_for_tool(language: str) -> str:
    return LANGUAGE_TOOL_LANG_MAP.get(language, DEFAULT_LANGUAGE_TOOL_LANG)


def correct_text(text: str, language: str) -> str:
    tool_language = normalize_language_for_tool(language)
    code = r'''
import language_tool_python

tool = language_tool_python.LanguageTool("'''+ tool_language + r'''")
try:
    print(tool.correct(r"""'''+ text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"') + r'''"""))
finally:
    tool.close()
'''
    proc = subprocess.run(
        [str(PYTHON_BIN), "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "No se pudo corregir el texto")
    return proc.stdout.strip()


def copy_to_clipboard(text: str) -> None:
    subprocess.run(["wl-copy"], input=text, text=True, check=False)


def type_text(text: str) -> bool:
    proc = subprocess.run(["wtype", text], check=False)
    return proc.returncode == 0


def start_mode() -> int:
    pid = start_recording()
    write_state({"pid": pid, "started_at": time.time()})
    play_sound(START_SOUND)
    notify("Voice Toggle", "Escuchando...")
    return 0


def stop_mode(state: dict) -> int:
    pid = int(state.get("pid", 0))
    stop_recording(pid)
    clear_state()
    notify("Voice Toggle", "Grabacion detenida. Procesando...")
    transcribe_started = time.monotonic()
    load_before = os.getloadavg()[0]

    if not RECORDING_FILE.exists() or RECORDING_FILE.stat().st_size < 2048:
        play_sound(DONE_SOUND)
        notify("Voice Toggle", "No detecte audio util.")
        return 1

    try:
        text, detected_language, language_probability = transcribe()
    except Exception as exc:
        append_perf_log({
            "timestamp": time.time(),
            "model": MODEL_NAME,
            "status": "transcription_error",
            "transcribe_seconds": round(time.monotonic() - transcribe_started, 3),
            "recording_seconds": round(time.time() - float(state.get("started_at", time.time())), 3),
            "load1_before": round(load_before, 2),
            "load1_after": round(os.getloadavg()[0], 2),
        })
        play_sound(DONE_SOUND)
        notify("Voice Toggle", f"Fallo la transcripcion: {exc}")
        return 1

    if not text:
        append_perf_log({
            "timestamp": time.time(),
            "model": MODEL_NAME,
            "status": "empty_text",
            "transcribe_seconds": round(time.monotonic() - transcribe_started, 3),
            "recording_seconds": round(time.time() - float(state.get("started_at", time.time())), 3),
            "load1_before": round(load_before, 2),
            "load1_after": round(os.getloadavg()[0], 2),
            "detected_language": detected_language,
            "language_probability": round(language_probability, 4),
        })
        play_sound(DONE_SOUND)
        notify("Voice Toggle", "No se detecto texto.")
        return 1

    correction_started = time.monotonic()
    try:
        corrected_text = correct_text(text, detected_language)
    except Exception as exc:
        corrected_text = text
        correction_seconds = round(time.monotonic() - correction_started, 3)
        notify("Voice Toggle", f"No se pudo corregir el texto. Uso transcripcion original: {exc}")
    else:
        correction_seconds = round(time.monotonic() - correction_started, 3)

    final_text = capitalize_first_letter(corrected_text or text)

    copy_to_clipboard(final_text)
    time.sleep(0.15)
    typed_ok = type_text(final_text)
    play_sound(DONE_SOUND)
    text_preview = preview_text(final_text)
    transcribe_seconds = round(time.monotonic() - transcribe_started, 3)
    recording_seconds = round(time.time() - float(state.get("started_at", time.time())), 3)
    load_after = round(os.getloadavg()[0], 2)

    append_perf_log({
        "timestamp": time.time(),
        "model": MODEL_NAME,
        "status": "typed_ok" if typed_ok else "clipboard_only",
        "transcribe_seconds": transcribe_seconds,
        "correction_seconds": correction_seconds,
        "recording_seconds": recording_seconds,
        "text_length": len(final_text),
        "corrected": final_text != text,
        "detected_language": detected_language,
        "language_probability": round(language_probability, 4),
        "languagetool_language": normalize_language_for_tool(detected_language),
        "load1_before": round(load_before, 2),
        "load1_after": load_after,
    })

    if typed_ok:
        notify("Voice Toggle", f"Texto pegado con exito [{detected_language}] ({transcribe_seconds}s): {text_preview}")
        return 0

    notify("Voice Toggle", f"No se pudo pegar. Guardado en el portapapeles [{detected_language}] ({transcribe_seconds}s): {text_preview}")
    return 1


def main() -> int:
    ensure_dirs()
    with open(LOCK_FILE, "w") as lock:
        try:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return 0

        state = read_state()
        pid = int(state.get("pid", 0)) if state else 0

        if pid and process_alive(pid):
            return stop_mode(state)

        clear_state()
        return start_mode()


if __name__ == "__main__":
    sys.exit(main())
