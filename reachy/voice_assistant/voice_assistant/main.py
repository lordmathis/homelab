import os
import threading
import time

import numpy as np
from reachy_mini import ReachyMini, ReachyMiniApp

from voice_assistant.expressions import ExpressionRunner
from voice_assistant.mikoshi_client import MikoshiClient
from voice_assistant.robot_api import ConversationState, start_robot_api
from voice_assistant.sounds import ensure_listening_cue
from voice_assistant.stt import transcribe
from voice_assistant.tts import synthesize
from voice_assistant.wake_word import WakeWordDetector
from voice_assistant.vad import VoiceActivityDetector


# Extra wait after the computed TTS duration before listening resumes.
# Covers GStreamer preroll + scheduling latency so we don't capture the tail
# of Reachy's own speech (echo) when VAD restarts.
PLAYBACK_TAIL_S = 0.5


class VoiceAssistantApp(ReachyMiniApp):
    custom_app_url: str | None = "http://0.0.0.0:8042"
    request_media_backend: str | None = None

    def __init__(self):
        super().__init__()
        self.daemon_on_localhost = False
        self._wake_word = None
        self._reachy = None
        self._expression_runner = None
        self._conversation_thread = None
        self._stop_event = threading.Event()
        self._mikoshi = MikoshiClient()
        self._state = ConversationState()
        self._cue_path = ensure_listening_cue()

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        print("[main] run() called, initializing robot...")
        self._reachy = reachy_mini
        self._stop_event = stop_event
        self._expression_runner = ExpressionRunner(reachy_mini)
        self._state.robot_connected = True

        start_robot_api(reachy_mini, self._expression_runner, self._state)

        reachy_mini.enable_motors()
        reachy_mini.wake_up()
        print("[main] Robot awake, starting wake word detector...")

        self._wake_word = WakeWordDetector(
            reachy_mini,
            on_detected=self._on_wake_word,
            threshold=0.7,
        )
        self._wake_word.start()
        print("[main] Say 'Hey Reachy!'")

        while not stop_event.is_set():
            time.sleep(0.1)

        self._wake_word.stop()

    def _on_wake_word(self):
        if self._conversation_thread and self._conversation_thread.is_alive():
            print("[main] Already in conversation, ignoring wake word")
            return

        self._wake_word.stop()
        self._conversation_thread = threading.Thread(
            target=self._run_conversation, daemon=True
        )
        self._conversation_thread.start()

    def _run_conversation(self):
        try:
            self._reachy.media.play_sound("wake_up.wav")
            self._expression_runner.play("greet")
            self._state.current = "listening"

            try:
                chat_id = self._mikoshi.new_session()
                print(f"[conversation] mikoshi chat={chat_id} Listening...")
            except Exception as e:
                print(f"[mikoshi] ERROR creating chat: {e}")
                self._state.current = "idle"
                self._wake_word.start()
                return

            last_speech_time = time.time()
            conversation_timeout = 10.0

            while not self._stop_event.is_set():
                vad = VoiceActivityDetector(
                    energy_threshold=0.02,
                    end_of_utterance_silence=1.5,
                    conversation_timeout=9999.0,
                    min_speech_duration=0.3,
                )
                audio_buffer: list[np.ndarray] = []

                while not self._stop_event.is_set():
                    if time.time() - last_speech_time > conversation_timeout:
                        print("[conversation] No speech for 10s, ending conversation")
                        self._expression_runner.play("reset")
                        self._state.current = "idle"
                        self._wake_word.start()
                        return

                    sample = self._reachy.media.get_audio_sample()
                    if sample is None:
                        time.sleep(0.01)
                        continue

                    result = vad.process_frame(sample)

                    if result["is_speech"]:
                        last_speech_time = time.time()

                    if result["is_speech"] or result["speech_duration"] > 0:
                        audio_buffer.append(sample)

                    if result["end_of_utterance"]:
                        print(f"[conversation] End of utterance (speech: {result['speech_duration']:.1f}s)")
                        if audio_buffer:
                            audio_data = np.concatenate(audio_buffer)
                            try:
                                text = transcribe(audio_data)
                                print(f"[stt] Transcription: {text!r}")
                                if text:
                                    self._expression_runner.play("thinking")
                                    self._state.current = "processing"

                                    def on_message(reply: str):
                                        print(f"[reachy] {reply}")
                                        try:
                                            tts_path, duration = synthesize(reply)
                                            self._state.current = "responding"
                                            try:
                                                self._reachy.media.play_sound(tts_path)
                                                time.sleep(duration + PLAYBACK_TAIL_S)
                                            finally:
                                                os.unlink(tts_path)
                                        except Exception as e:
                                            print(f"[tts] ERROR playing message: {e}")

                                    self._mikoshi.send_message(text, on_message=on_message)
                                    self._reachy.media.play_sound(self._cue_path)
                            except Exception as e:
                                print(f"[mikoshi] ERROR: {e}")
                        last_speech_time = time.time()
                        self._state.current = "listening"
                        break

                print("[conversation] Listening again...")
        except Exception as e:
            print(f"[conversation] ERROR: {e}")
            self._state.current = "idle"
            self._wake_word.start()

    def stop(self):
        if self._wake_word:
            self._wake_word.stop()
        super().stop()


if __name__ == "__main__":
    app = VoiceAssistantApp()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
